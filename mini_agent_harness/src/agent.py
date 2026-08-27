# src/agent.py
from src.model import LLM, Message, ToolCall , RunResult
from src.tools.registry import ToolRegistry
import asyncio

class Agent:
    def __init__(self, llm: LLM,
                 tools: ToolRegistry,
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

    async def run(self, user_input: str) -> RunResult:
        history: list[Message] = [Message(type="user", text=user_input)]
        tokens_used = 0

        for iteration in range(self.max_iterations):
            response = await self.llm.generate(history)
            tokens_used += response.tokens_used
        
            if tokens_used > self.max_tokens:
                return RunResult(
                    status="budget_exceeded",
                    iterations_used=iteration + 1,
                    tokens_used=tokens_used,
                )
            # Always record what the model said/decided
            history.append(response.content)

            if response.type == "final":
                return RunResult(
                    status="completed",
                    output=response.content.text,
                    iterations_used=iteration + 1,
                    tokens_used=tokens_used,
                    )

            if response.type == "tool_call":
                if response.tool_call is None:
                    # Model claimed a tool_call but gave us nothing to run
                    history.append(Message(
                        type="system",
                        text="Error: tool_call response missing 'tool_call' field"
                    ))
                    continue

                result = await self._execute_tool_with_retry(response.tool_call)
                history.append(Message(
                    type="system",
                    text=f"Tool '{response.tool_call.name}' result: {result}"
                ))
                continue

            history.append(Message(type="system", text=f"Error: unrecognized response type '{response.type}'"))

        return RunResult(
            status="max_iterations_exceeded",
            iterations_used=self.max_iterations,
            tokens_used=tokens_used,
        )

    async def _execute_tool_with_retry(self, tool_call: ToolCall) -> str:
        last_error = "unknown error"
        attempts = self.max_tool_retries + 1  # 1 initial try + 2 retries = 3 total

        for attempt in range(attempts):
            try:
                return await asyncio.wait_for(
                    self.tools.execute(tool_call.name, tool_call.arguments),
                    timeout=self.tool_timeout_seconds,
                )
            except ValueError as e:
                # Unknown tool name — retrying won't help, fail immediately
                return f"Error: {e}"
            except asyncio.TimeoutError:
                last_error = f"timed out after {self.tool_timeout_seconds}s"
            except Exception as e:
                last_error = f"failed — {e}"

            if attempt < attempts - 1:
                await asyncio.sleep(0.5 * (2 ** attempt))  # 0.5s, 1s backoff

        return f"Error: tool '{tool_call.name}' {last_error} (after {attempts} attempts)"