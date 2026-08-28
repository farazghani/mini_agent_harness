import asyncio

from src.model import Message , LLMResponse , ToolCall
from src.llm.mockllm import MockLLM


async def main():
    canned_response = LLMResponse(
        type="final",
        content=Message(type="model", text="Hi, this is a mocked reply!")
    )

    llm = MockLLM(response=canned_response)

    message = Message(
        type="user",
        text="Hello"
    )

    response = await llm.generate(message)
    print(response)

    tool_call_response = LLMResponse(
        type="tool_call",
        content=Message(type="model", text="Let me check that for you."),
        tool_call=ToolCall(name="search", arguments={"query": "weather today"})
    )
    llm2 = MockLLM(response=tool_call_response)
    response2 = await llm2.generate(message)
    print(response2)

asyncio.run(main())
