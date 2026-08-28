# src/test/agent_test.py
import asyncio
import os
import tempfile

from src.model import Message, LLMResponse, ToolCall, Tool
from src.llm.mockllm import MockLLM , CrashingMockLLM
from src.tools.registry import ToolRegistry
from src.tools.calculator import CalculatorTool
from src.agent import Agent
from src.db.store import EventStore


def fresh_store() -> tuple[EventStore, str]:
    """Creates a new temp SQLite file per test so tests don't share state."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # EventStore creates the schema itself on first use
    return EventStore(path), path


def cleanup(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)


async def test_simple_final_response():
    """LLM answers immediately with no tool calls."""
    store, db_path = fresh_store()
    llm = MockLLM(response=[
        LLMResponse(
            type="final",
            content=Message(type="model", text="Hello there!"),
            tokens_used=10
        )
    ])
    agent = Agent(llm=llm, tools=ToolRegistry([]), store=store, max_iterations=10)

    result = await agent.start("Hi")

    assert result.status == "completed"
    assert result.output == "Hello there!"
    assert result.iterations_used == 1
    assert result.tokens_used == 10
    assert len(llm.calls) == 1

    cleanup(db_path)
    print("test_simple_final_response passed")


async def test_tool_call_then_final():
    """LLM calls a tool, sees the result, then gives a final answer."""
    store, db_path = fresh_store()
    llm = MockLLM(response=[
        LLMResponse(
            type="tool_call",
            content=Message(type="model", text="Let me calculate that."),
            tool_call=ToolCall(name="calculator", arguments={"expression": "6 * 7"}),
            tokens_used=15
        ),
        LLMResponse(
            type="final",
            content=Message(type="model", text="The answer is 42."),
            tokens_used=10
        ),
    ])
    tools = ToolRegistry([CalculatorTool()])
    agent = Agent(llm=llm, tools=tools, store=store, max_iterations=10)

    result = await agent.start("What is 6 times 7?")

    assert result.status == "completed"
    assert result.output == "The answer is 42."
    assert result.iterations_used == 2
    assert result.tokens_used == 25
    assert len(llm.calls) == 2

    second_call_history = llm.calls[1]
    assert len(second_call_history) == 3
    assert second_call_history[0].type == "user"
    assert second_call_history[1].type == "model"
    assert second_call_history[2].type == "system"
    assert "Tool 'calculator' result:" in second_call_history[2].text

    cleanup(db_path)
    print("test_tool_call_then_final passed")


async def test_unknown_tool_name():
    """LLM calls a tool that doesn't exist in the registry."""
    store, db_path = fresh_store()
    llm = MockLLM(response=[
        LLMResponse(
            type="tool_call",
            content=Message(type="model", text="Using a tool."),
            tool_call=ToolCall(name="nonexistent_tool", arguments={}),
            tokens_used=10
        ),
        LLMResponse(
            type="final",
            content=Message(type="model", text="I couldn't find that tool."),
            tokens_used=10
        ),
    ])
    tools = ToolRegistry([])
    agent = Agent(llm=llm, tools=tools, store=store, max_iterations=10)

    result = await agent.start("Do something")

    assert result.status == "completed"
    assert result.output == "I couldn't find that tool."
    second_call_history = llm.calls[1]
    assert "Error" in second_call_history[-1].text

    cleanup(db_path)
    print("test_unknown_tool_name passed")


async def test_max_iterations_reached():
    """LLM keeps calling tools forever and never returns 'final'."""
    store, db_path = fresh_store()
    infinite_tool_call = LLMResponse(
        type="tool_call",
        content=Message(type="model", text="Calling again."),
        tool_call=ToolCall(name="calculator", arguments={"expression": "1 + 1"}),
        tokens_used=5
    )
    llm = MockLLM(response=[infinite_tool_call] * 20)
    tools = ToolRegistry([CalculatorTool()])
    agent = Agent(llm=llm, tools=tools, store=store, max_iterations=10)

    result = await agent.start("Loop forever")

    assert result.status == "max_iterations_exceeded"
    assert result.output is None
    assert result.iterations_used == 10
    assert len(llm.calls) == 10

    cleanup(db_path)
    print("test_max_iterations_reached passed")


async def test_malformed_tool_call_response():
    """LLM says type='tool_call' but forgets to include tool_call itself."""
    store, db_path = fresh_store()
    llm = MockLLM(response=[
        LLMResponse(
            type="tool_call",
            content=Message(type="model", text="Oops, forgot the tool_call field."),
            tool_call=None,
            tokens_used=10
        ),
        LLMResponse(
            type="final",
            content=Message(type="model", text="Recovered."),
            tokens_used=10
        ),
    ])
    agent = Agent(llm=llm, tools=ToolRegistry([]), store=store, max_iterations=10)

    result = await agent.start("Test malformed response")

    assert result.status == "completed"
    assert result.output == "Recovered."
    second_call_history = llm.calls[1]
    assert "missing" in second_call_history[-1].text.lower()

    cleanup(db_path)
    print("test_malformed_tool_call_response passed")


async def test_budget_exceeded():
    """LLM's token usage crosses max_tokens before finishing."""
    store, db_path = fresh_store()
    llm = MockLLM(response=[
        LLMResponse(
            type="final",
            content=Message(type="model", text="This should never be seen."),
            tokens_used=9999
        )
    ])
    agent = Agent(llm=llm, tools=ToolRegistry([]), store=store, max_iterations=10, max_tokens=1000)

    result = await agent.start("Say something expensive")

    assert result.status == "budget_exceeded"
    assert result.output is None
    assert result.tokens_used == 9999
    assert result.iterations_used == 1

    cleanup(db_path)
    print("test_budget_exceeded passed")


class FlakyTool(Tool):
    """Fails a fixed number of times, then succeeds — for testing retry logic."""

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.attempts = 0

    @property
    def name(self) -> str:
        return "flaky"

    @property
    def description(self) -> str:
        return "A test tool that fails a configurable number of times before succeeding."

    async def execute(self, arguments: dict) -> str:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise RuntimeError("simulated transient failure")
        return "success"


async def test_tool_retry_then_success():
    """Tool fails twice, succeeds on the 3rd (final allowed) attempt."""
    store, db_path = fresh_store()
    flaky = FlakyTool(fail_times=2)
    llm = MockLLM(response=[
        LLMResponse(
            type="tool_call",
            content=Message(type="model", text="Calling flaky tool."),
            tool_call=ToolCall(name="flaky", arguments={}),
            tokens_used=10
        ),
        LLMResponse(
            type="final",
            content=Message(type="model", text="Done."),
            tokens_used=10
        ),
    ])
    agent = Agent(llm=llm, tools=ToolRegistry([flaky]), store=store, max_iterations=10, max_tool_retries=2)

    result = await agent.start("Use the flaky tool")

    assert result.status == "completed"
    assert flaky.attempts == 3
    second_call_history = llm.calls[1]
    assert "success" in second_call_history[-1].text

    cleanup(db_path)
    print("test_tool_retry_then_success passed")


async def test_tool_fails_all_retries():
    """Tool fails every attempt — error reported back, run does not crash."""
    store, db_path = fresh_store()
    flaky = FlakyTool(fail_times=99)
    llm = MockLLM(response=[
        LLMResponse(
            type="tool_call",
            content=Message(type="model", text="Calling flaky tool."),
            tool_call=ToolCall(name="flaky", arguments={}),
            tokens_used=10
        ),
        LLMResponse(
            type="final",
            content=Message(type="model", text="Gave up."),
            tokens_used=10
        ),
    ])
    agent = Agent(llm=llm, tools=ToolRegistry([flaky]), store=store, max_iterations=10, max_tool_retries=2)

    result = await agent.start("Use the flaky tool")

    assert result.status == "completed"
    assert flaky.attempts == 3
    second_call_history = llm.calls[1]
    assert "Error" in second_call_history[-1].text

    cleanup(db_path)
    print("test_tool_fails_all_retries passed")


class HangingTool(Tool):
    """Never returns — for testing the per-tool-call timeout."""

    @property
    def name(self) -> str:
        return "hanging"

    @property
    def description(self) -> str:
        return "hanging tool"

    async def execute(self, arguments: dict) -> str:
        await asyncio.sleep(999)
        return "never gets here"


async def test_tool_timeout():
    """Tool hangs forever — timeout kicks in, error reported, run does not hang."""
    store, db_path = fresh_store()
    hanging = HangingTool()
    llm = MockLLM(response=[
        LLMResponse(
            type="tool_call",
            content=Message(type="model", text="Calling hanging tool."),
            tool_call=ToolCall(name="hanging", arguments={}),
            tokens_used=10
        ),
        LLMResponse(
            type="final",
            content=Message(type="model", text="Timed out, moving on."),
            tokens_used=10
        ),
    ])
    agent = Agent(
        llm=llm,
        tools=ToolRegistry([hanging]),
        store=store,
        max_iterations=10,
        tool_timeout_seconds=0.2,
        max_tool_retries=1,
    )

    result = await agent.start("Use the hanging tool")

    assert result.status == "completed"
    second_call_history = llm.calls[1]
    assert "timed out" in second_call_history[-1].text.lower()

    cleanup(db_path)
    print("test_tool_timeout passed")


# --- NEW: tests specific to persistence/resumability ---

async def test_events_are_persisted():
    """Every LLM response and tool result should show up as a stored event."""
    store, db_path = fresh_store()
    llm = MockLLM(response=[
        LLMResponse(
            type="tool_call",
            content=Message(type="model", text="Calculating."),
            tool_call=ToolCall(name="calculator", arguments={"expression": "2 + 2"}),
            tokens_used=10
        ),
        LLMResponse(
            type="final",
            content=Message(type="model", text="It's 4."),
            tokens_used=10
        ),
    ])
    agent = Agent(llm=llm, tools=ToolRegistry([CalculatorTool()]), store=store)
    result = await agent.start("What is 2 + 2?")

    run_id = store.list_incomplete_runs()  # won't include this run since it's completed
    # Fetch run_id properly: query all runs directly since start() doesn't return it
    # (only RunResult is returned) — so grab it via a raw query instead.
    import sqlite3
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT id FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    run_id = row[0]

    events = store.get_events(run_id)
    event_types = [e["event_type"] for e in events]

    assert "run_created" in event_types
    assert "llm_response" in event_types
    assert "tool_call_attempt" in event_types
    assert event_types.count("llm_response") == 2  # one per iteration

    cleanup(db_path)
    print("test_events_are_persisted passed")




async def main():
    await test_simple_final_response()
    await test_tool_call_then_final()
    await test_unknown_tool_name()
    await test_max_iterations_reached()
    await test_malformed_tool_call_response()
    await test_budget_exceeded()
    await test_tool_retry_then_success()
    await test_tool_fails_all_retries()
    await test_tool_timeout()
    await test_events_are_persisted()
    print("\nAll tests passed!")


if __name__ == "__main__":
    asyncio.run(main())