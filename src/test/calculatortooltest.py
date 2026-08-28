import asyncio
from src.tools.calculator import CalculatorTool


async def main():
    tool = CalculatorTool()
    print(await tool.execute({"expression": "2 + 2"}))       # 4
    print(await tool.execute({"expression": "(3 + 4) * 2"})) # 14
    print(await tool.execute({"expression": "10 / 0"}))      # Error: division by zero
    print(await tool.execute({"expression": "__import__('os')"}))  # Error: invalid expression


asyncio.run(main())

