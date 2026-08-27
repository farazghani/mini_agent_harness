from src.model import Tool

class ToolRegistry:

    def __init__(self, tools: list[Tool]):
        self.tools = {
            tool.name: tool
            for tool in tools
        }


    async def execute(self, name: str, arguments: dict) -> str:
                tool = self.tools.get(name)
                if tool is None:
                    return f"Error: unknown tool '{name}'"
                return await tool.execute(arguments)