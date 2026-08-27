# src/test/agent_test.py
import asyncio

from src.model import Message, LLMResponse, ToolCall
from src.llm.mockllm import MockLLM
from src.tools.registry import ToolRegistry
from src.tools.calculator import CalculatorTool
from src.agent import Agent


async def test_simple_final_response():
    """LLM answers immediately with no tool calls."""
    llm = MockLLM(response=[
        LLMResponse(
            type="final",
            content=Message(type="model", text="Hello there!")
        )
    ])
    agent = Agent(llm=llm, tools=ToolRegistry([]), max_iterations=10)

    result = await agent.run("Hi")

    assert result == "Hello there!"
    # Should have called generate exactly once
    assert len(llm.calls) == 1
    print("test_simple_final_response passed")


async def test_tool_call_then_final():
    """LLM calls a tool, sees the result, then gives a final answer."""
    llm = MockLLM(response=[
        LLMResponse(
            type="tool_call",
            content=Message(type="model", text="Let me calculate that."),
            tool_call=ToolCall(name="calculator", arguments={"expression": "6 * 7"})
        ),
        LLMResponse(
            type="final",
            content=Message(type="model", text="The answer is 42.")
        ),
    ])
    tools = ToolRegistry([CalculatorTool()])
    agent = Agent(llm=llm, tools=tools, max_iterations=10)

    result = await agent.run("What is 6 times 7?")

    assert result == "The answer is 42."
    assert len(llm.calls) == 2  # generate() called twice

    # Check the history sent on the SECOND call includes the tool result
    second_call_history = llm.calls[1]
    assert len(second_call_history) == 3
    assert second_call_history[0].type == "user"
    assert second_call_history[1].type == "model"
    assert second_call_history[2].type == "system"
    assert "42" in second_call_history[2].text
    print("test_tool_call_then_final passed")


async def test_unknown_tool_name():
    """LLM calls a tool that doesn't exist in the registry."""
    llm = MockLLM(response=[
        LLMResponse(
            type="tool_call",
            content=Message(type="model", text="Using a tool."),
            tool_call=ToolCall(name="nonexistent_tool", arguments={})
        ),
        LLMResponse(
            type="final",
            content=Message(type="model", text="I couldn't find that tool.")
        ),
    ])
    tools = ToolRegistry([])  # empty registry
    agent = Agent(llm=llm, tools=tools, max_iterations=10)

    result = await agent.run("Do something")

    assert result == "I couldn't find that tool."
    # Check the error got fed back into history
    second_call_history = llm.calls[1]
    assert "Error" in second_call_history[-1].text
    print("test_unknown_tool_name passed")


async def test_max_iterations_reached():
    """LLM keeps calling tools forever and never returns 'final'."""
    # Always return a tool_call response, never 'final'
    infinite_tool_call = LLMResponse(
        type="tool_call",
        content=Message(type="model", text="Calling again."),
        tool_call=ToolCall(name="calculator", arguments={"expression": "1 + 1"})
    )
    llm = MockLLM(response=[infinite_tool_call] * 20)  # more than max_iterations
    tools = ToolRegistry([CalculatorTool()])
    agent = Agent(llm=llm, tools=tools, max_iterations=10)

    result = await agent.run("Loop forever")

    assert result == "Error: max iterations reached without a final response"
    assert len(llm.calls) == 10  # stopped exactly at max_iterations
    print("test_max_iterations_reached passed")


async def test_malformed_tool_call_response():
    """LLM says type='tool_call' but forgets to include tool_call itself."""
    llm = MockLLM(response=[
        LLMResponse(
            type="tool_call",
            content=Message(type="model", text="Oops, forgot the tool_call field."),
            tool_call=None
        ),
        LLMResponse(
            type="final",
            content=Message(type="model", text="Recovered.")
        ),
    ])
    agent = Agent(llm=llm, tools=ToolRegistry([]), max_iterations=10)

    result = await agent.run("Test malformed response")

    assert result == "Recovered."
    second_call_history = llm.calls[1]
    assert "missing" in second_call_history[-1].text.lower()
    print("test_malformed_tool_call_response passed")


async def main():
    await test_simple_final_response()
    await test_tool_call_then_final()
    await test_unknown_tool_name()
    await test_max_iterations_reached()
    await test_malformed_tool_call_response()
    print("\nAll tests passed!")


if __name__ == "__main__":
    asyncio.run(main())