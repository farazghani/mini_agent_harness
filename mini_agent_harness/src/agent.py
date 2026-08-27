# src/agent.py
from src.model import LLM, Message, ToolCall
from src.tools.registry import ToolRegistry


class Agent:
    def __init__(self, llm: LLM, tools: ToolRegistry, max_iterations: int = 10):
        self.llm = llm
        self.tools = tools
        self.max_iterations = max_iterations

    async def run(self, user_input: str) -> str:
        history: list[Message] = [Message(type="user", text=user_input)]

        for iteration in range(self.max_iterations):
            response = await self.llm.generate(history)

            # Always record what the model said/decided
            history.append(response.content)

            if response.type == "final":
                return response.content.text

            if response.type == "tool_call":
                if response.tool_call is None:
                    # Model claimed a tool_call but gave us nothing to run
                    history.append(Message(
                        type="system",
                        text="Error: tool_call response missing 'tool_call' field"
                    ))
                    continue

                result = await self._execute_tool(response.tool_call)

                # Feed the tool's result back into the conversation
                history.append(Message(
                    type="system",
                    text=f"Tool '{response.tool_call.name}' result: {result}"
                ))
                continue

            # Unknown response type — shouldn't happen given the Literal,
            # but guard anyway in case of bad data.
            history.append(Message(
                type="system",
                text=f"Error: unrecognized response type '{response.type}'"
            ))

        return "Error: max iterations reached without a final response"

    async def _execute_tool(self, tool_call: ToolCall) -> str:
        try:
            return await self.tools.execute(tool_call.name, tool_call.arguments)
        except Exception as e:
            return f"Error: tool execution failed — {e}"