# src/agent.py
from src.model import LLM, Message, ToolCall , RunResult
from src.tools.registry import ToolRegistry
import asyncio
from src.db.store import EventStore

class Agent:
    def __init__(self, llm: LLM,
                 tools: ToolRegistry,
                 store: EventStore,
                 max_iterations: int = 10,
                 max_tokens: int = 10_000,
                 tool_timeout_seconds: float = 5.0,
                 max_tool_retries: int = 2,
                 ):
        self.llm = llm
        self.tools = tools
        self.max_iterations = max_iterations
        self.tool_timeout_seconds = tool_timeout_seconds
        self.max_tool_retries = max_tool_retries
        self.max_tokens = max_tokens
        self.store = store
    
    #create a new run
    async def start(self , user_input: str) -> RunResult:
        run_id = self.store.create_run(user_input)
        return await self._execute(run_id)
    #continue a run
    async def resume(self, run_id: str) -> RunResult:
        run = self.store.get_run(run_id)
        if run is None:
            raise ValueError(f"Unknown run_id: {run_id}")
        if run["status"] != "running":
            # Already finished , report what happened, don't redo work
            return RunResult(
                status=run["status"],
                output=run["output"],
                iterations_used=run["iterations_used"],
                tokens_used=run["tokens_used"],
            )
        return await self._execute(run_id)
    
    #replay the history 
    """
    get events from run
    store it in history 
    calculates total token
    stores no. of iterations

     """
    def _replay_history(self, run_id: str) -> tuple[list[Message], int, int]:
        """Rebuild history, tokens_used, and iterations completed from the event log."""
        events = self.store.get_events(run_id)
        history: list[Message] = []
        tokens_used = 0
        iterations_completed = 0

        for event in events:
            payload = event["payload"]
            if event["event_type"] == "run_created":
                history.append(Message(type="user", text=payload["user_input"]))
            elif event["event_type"] == "llm_response":
                history.append(Message(**payload["content"]))
                tokens_used += payload["tokens_used"]
                iterations_completed += 1
            elif event["event_type"] == "tool_result":
                history.append(Message(type="system", text=payload["message_text"]))

        return history, tokens_used, iterations_completed
    



    async def _execute(self, run_id: str) -> RunResult:
        #taking record from db
        history, tokens_used, iterations_completed = self._replay_history(run_id)
        #feeding
        for iteration in range(iterations_completed, self.max_iterations):
            response = await self.llm.generate(history)
            tokens_used += response.tokens_used
            #appending response back to db
            self.store.append_event(run_id, "llm_response", {
                "type": response.type,
                "content": response.content.model_dump(),
                "tool_call": response.tool_call.model_dump() if response.tool_call else None,
                "tokens_used": response.tokens_used,
            })
            #condtion check
            if tokens_used > self.max_tokens:
                self.store.update_run_status(
                    run_id, "budget_exceeded",
                    iterations_used=iteration + 1, tokens_used=tokens_used
                )
                return RunResult(status="budget_exceeded", iterations_used=iteration + 1, tokens_used=tokens_used)
            #also appending in running state -> history
            history.append(response.content)

            if response.type == "final":
                self.store.update_run_status(
                    run_id, "completed", output=response.content.text,
                    iterations_used=iteration + 1, tokens_used=tokens_used
                )
                return RunResult(
                    status="completed", output=response.content.text,
                    iterations_used=iteration + 1, tokens_used=tokens_used
                )
            #previous iteration
            if response.type == "tool_call":
                if response.tool_call is None:
                    msg_text = "Error: tool_call response missing 'tool_call' field"
                    history.append(Message(type="system", text=msg_text))
                    self.store.append_event(run_id, "tool_result", {"message_text": msg_text})
                    continue

                result = await self._execute_tool_with_retry(run_id, response.tool_call)
                msg_text = f"Tool '{response.tool_call.name}' result: {result}"
                history.append(Message(type="system", text=msg_text))
                self.store.append_event(run_id, "tool_result", {"message_text": msg_text})
                continue

            msg_text = f"Error: unrecognized response type '{response.type}'"
            history.append(Message(type="system", text=msg_text))
            self.store.append_event(run_id, "tool_result", {"message_text": msg_text})

        self.store.update_run_status(
            run_id, "max_iterations_exceeded",
            iterations_used=self.max_iterations, tokens_used=tokens_used
        )
        return RunResult(status="max_iterations_exceeded", iterations_used=self.max_iterations, tokens_used=tokens_used)




    async def _execute_tool_with_retry(self, run_id: str, tool_call: ToolCall) -> str:
        last_error = "unknown error"
        attempts = self.max_tool_retries + 1

        for attempt in range(attempts):
            self.store.append_event(run_id, "tool_call_attempt", {
                "tool": tool_call.name, "arguments": tool_call.arguments, "attempt": attempt + 1
            })
            try:
                result = await asyncio.wait_for(
                    self.tools.execute(tool_call.name, tool_call.arguments),
                    timeout=self.tool_timeout_seconds,
                )
                self.store.append_event(run_id, "tool_call_success", {"tool": tool_call.name, "result": result})
                return result
            #from ai
            except ValueError as e:
                self.store.append_event(run_id, "tool_call_error", {"tool": tool_call.name, "error": str(e), "attempt": attempt + 1})
                return f"Error: {e}"
            except asyncio.TimeoutError:
                last_error = f"timed out after {self.tool_timeout_seconds}s"
                self.store.append_event(run_id, "tool_call_error", {"tool": tool_call.name, "error": last_error, "attempt": attempt + 1})
            except Exception as e:
                last_error = f"failed — {e}"
                self.store.append_event(run_id, "tool_call_error", {"tool": tool_call.name, "error": last_error, "attempt": attempt + 1})

            if attempt < attempts - 1:
                self.store.append_event(run_id, "tool_call_retry_wait", {"seconds": 0.5 * (2 ** attempt)})
                await asyncio.sleep(0.5 * (2 ** attempt))
        #exhausted attempts
        return f"Error: tool '{tool_call.name}' {last_error} (after {attempts} attempts)"
