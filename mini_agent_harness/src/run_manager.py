# src/run_manager.py
import asyncio

from src.db.store import EventStore
from src.eventbus import EventBus, PublishingEventStore
from src.agent import Agent
from src.llm.mockllm import MockLLM
from src.model import LLMResponse, Message
from src.tools.registry import ToolRegistry
from src.tools.calculator import CalculatorTool
from src.tools.get_time import GetTimeTool
from src.tools.read_file import ReadFileTool


class RunManager:
    def __init__(self, db_path: str = "runs.db", max_concurrent: int = 3):
        raw_store = EventStore(db_path)
        self.bus = EventBus()
        self.store = PublishingEventStore(raw_store, self.bus)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.tools = ToolRegistry([
            CalculatorTool(),
            GetTimeTool(),
            ReadFileTool(base_dir="./sandbox"),
        ])

    def _make_llm(self) -> MockLLM:
        # Placeholder — swap for a real LLM implementation (e.g. AnthropicLLM)
        # once that's built. Kept as MockLLM here so the harness runs standalone.
        return MockLLM(response=[
            LLMResponse(type="final", content=Message(type="model", text="(mock) task complete."), tokens_used=10)
        ])

    async def start_run(self, task: str) -> str:
        run_id = self.store.create_run(task, status="queued")
        asyncio.create_task(self._execute(run_id))
        return run_id

    async def resume_incomplete_runs(self) -> None:
        """Call on app startup — picks up any run left in 'running' when the process died."""
        for run_id in self.store.list_incomplete_runs():
            asyncio.create_task(self._execute(run_id))


    async def _execute(self, run_id: str) -> None:
        # Waits here if 3 runs are already in flight — this IS the "queued" state,
        # visible via GET /runs/:id showing status="queued" until the semaphore frees up.
        async with self.semaphore:
            self.store.update_run_status(run_id, "running")
            agent = Agent(llm=self._make_llm(), tools=self.tools, store=self.store)
            await agent.resume(run_id)

