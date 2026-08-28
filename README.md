
Readme · MD
# mini_agent_harness
 
A minimal, durable agent execution harness: an LLM-driven tool-calling loop, exposed over
FastAPI, with full event-sourced persistence and crash/resume support.
 
## Architecture
 
```
.
├── src/
│   ├── model.py              # Pydantic models: Message, LLMResponse, ToolCall,
│   │                          # RunResult, RunStatus; LLM and Tool abstract base classes
│   ├── agent.py               # Agent — the core loop (start / resume / replay / retry)
│   ├── run_manager.py         # RunManager — concurrency cap, run lifecycle, LLM wiring
│   ├── eventbus.py             # EventBus (live pub/sub) + PublishingEventStore
│   │                          # (wraps EventStore so writes also push to SSE listeners)
│   ├── main.py                 # FastAPI app factory: POST /runs, GET /runs/:id, /stream
│   │
│   ├── db/
│   │   └── store.py           # EventStore — SQLite-backed event log (source of truth)
│   │
│   ├── llm/
│   │   └── mockllm.py          # MockLLM — scripted LLM for tests/demo (no real API yet)
│   │
│   ├── tools/
│   │   ├── registry.py         # ToolRegistry — dispatches tool calls by name
│   │   ├── calculator.py       # CalculatorTool — safe ast-based eval, 20% simulated failure
│   │   ├── get_time.py         # GetTimeTool
│   │   └── read_file.py        # ReadFileTool — sandboxed to a base_dir, blocks path traversal
│   │
│   └── test/
│       ├── agent_test.py       # Unit tests: loop behavior, retries, timeout, persistence
│       ├── e2e_test.py          # HTTP-level tests via FastAPI TestClient
│       └── kill_resume_test.py  # Subprocess kill + restart — proves resumability
│
├── sandbox/                    # Scratch dir ReadFileTool is sandboxed to
├── demo.sh                     # Scripted walkthrough: success / retries / kill+resume
├── pyproject.toml
└── runs.db                     # Default SQLite event log (gitignored)
```
```
                     ┌─────────────────────────────┐
                     │        FastAPI (main.py)     │
                     │  POST /runs                  │
                     │  GET  /runs/:id               │
                     │  GET  /runs/:id/stream (SSE)  │
                     └───────────────┬───────────────┘
                                     │
                     ┌───────────────▼───────────────┐
                     │         RunManager             │
                     │  asyncio.Semaphore(3)          │  ← concurrency cap
                     │  queues extra runs              │
                     └───────────────┬───────────────┘
                                     │ spawns one task per run
                     ┌───────────────▼───────────────┐
                     │            Agent               │
                     │  start() / resume()             │
                     │  loop: LLM → tool? → LLM → ...  │
                     │  retry + backoff, timeout,      │
                     │  budget + max-iteration guards  │
                     └──────┬──────────────────┬──────┘
                            │                  │
              ┌─────────────▼───────┐   ┌──────▼───────────┐
              │   LLM (abstract)     │   │  ToolRegistry      │
              │   MockLLM (impl)     │   │  → CalculatorTool   │
              └───────────────────────┘   │  → GetTimeTool      │
                                          │  → ReadFileTool      │
                                          └──────────────────────┘
                            │
              ┌─────────────▼─────────────────────┐
              │      PublishingEventStore           │
              │  writes to SQLite (EventStore) AND  │
              │  publishes to EventBus (live SSE)   │
              └─────────────┬────────────────────────┘
                            │
                     ┌──────▼──────┐
                     │  SQLite DB   │  ← source of truth, survives process death
                     │  runs table  │
                     │  events table│
                     └─────────────┘
```
 
**The core idea:** every meaningful step of a run (LLM response, tool attempt, tool
result, error, retry) is written to SQLite *before* the loop moves on. The in-memory
conversation `history` is just a projection of that log. This makes the whole system
resumable: on restart, the log is replayed to rebuild `history` and the loop continues
from the next un-persisted iteration — it never re-runs work that was already
completed and recorded.
 
## Agent loop
 
- Sends the full conversation `history` to the LLM every iteration (not just the
  latest message) — this is what gives the LLM memory of prior tool calls/results.
- On `type: "final"` → run ends, status `completed`.
- On `type: "tool_call"` → dispatches via `ToolRegistry`, feeds the result back into
  `history` as a `system` message, loops again.
- Hard caps: `max_iterations` (default 10) → `max_iterations_exceeded`; a mock
  token budget (`max_tokens`) checked after every LLM call → `budget_exceeded`.
- Tool calls run under `asyncio.wait_for(..., timeout=tool_timeout_seconds)` so a
  hanging tool can never stall a run — timeouts convert to a retryable error.
- Failed tool calls retry with exponential backoff (`max_tool_retries`, default 2 →
  3 total attempts, 0.5s/1s backoff). Exhausted retries report the error back to the
  LLM as a normal tool result — the run never crashes on a tool failure.
- Unexpected exceptions in a run are caught at the `RunManager` level and persisted
  as a `run_error` event with status `failed`, rather than dying silently in a
  background task.
## Resumability
 
- `Agent._replay_history` reads only `run_created`, `llm_response`, and
  `tool_result` events (in order) to rebuild `history`, running token total, and
  number of completed iterations.
- `_execute`'s loop starts at `range(iterations_completed, max_iterations)` — so a
  restart skips every iteration that already has a persisted `llm_response`.
- On process startup, `RunManager.resume_incomplete_runs()` finds every run still
  `queued` or `running` in the DB and re-enters the loop for it.
- Proven by `src/test/kill_resume_test.py`: starts a real `uvicorn` subprocess,
  `SIGKILL`s it mid-run, starts a fresh subprocess against the same SQLite file, and
  asserts the run reaches `completed` — with the pre-kill events still present in
  its history.
## API
 
| Endpoint | Description |
|---|---|
| `POST /runs` `{"task": "..."}` | Creates a run (`status: queued`), executes asynchronously, returns `run_id` immediately. |
| `GET /runs/{run_id}` | Current status + full event history. |
| `GET /runs/{run_id}/stream` | SSE stream — replays past events, then streams live ones until the run finishes. |
 
**Concurrency:** at most 3 runs execute at once (`asyncio.Semaphore(3)` in
`RunManager`). Additional runs are created immediately with `status: queued` and
begin executing as soon as a slot frees up.
 
## Running
 
```bash
uv sync
uvicorn src.main:app --reload
```
 
```bash
curl -X POST localhost:8000/runs -H "Content-Type: application/json" \
  -d '{"task": "what is 6 times 7?"}'
 
curl localhost:8000/runs/<run_id>
curl -N localhost:8000/runs/<run_id>/stream
```
 
## Tests
 
```bash
pytest src/test/ -v -s
```
 
- `src/test/agent_test.py` — unit tests for the loop itself: final responses, tool
  calls, unknown tools, malformed responses, max-iterations, budget limits, tool
  retry/backoff, tool timeout, event persistence, and an in-process resumability
  test (two `Agent` instances sharing one SQLite file).
- `src/test/e2e_test.py` — HTTP-level tests via FastAPI's `TestClient`: a successful
  run end to end, 404 on unknown run, the SSE stream, and the concurrency cap.
- `src/test/kill_resume_test.py` — the hard requirement: a real subprocess is
  killed mid-run and a fresh subprocess resumes and completes it.
## Demo
 
```bash
./demo.sh
```
 
Walks through, with real API output:
1. A successful run (full event log printed).
2. A run exercising the tool-call → retry path (`CalculatorTool` has a built-in 20%
   simulated failure rate).
3. Kill the server mid-run (`SIGKILL`), restart it against the same DB file, and show
   the run completing from where it left off.
## Known limitations / next steps
 
- `RunManager._make_llm()` currently returns a scripted `MockLLM` for every run —
  there's no real LLM provider wired in yet. Swapping in a real `LLM` implementation
  (e.g. calling the Anthropic API) is the natural next step; nothing else in the
  loop, store, or API needs to change, since `tokens_used` is designed to be read
  straight off a real provider's usage response.
- Resumability granularity is "one full LLM iteration" — if a crash happens mid
  tool-retry-sequence (before that iteration's `llm_response`/`tool_result` event is
  written), that iteration's tool call is retried from attempt 1 on resume rather
  than resuming from the exact attempt number. This is a deliberate simplicity
  trade-off, not a bug.
