from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Literal , Any , Dict


class Message(BaseModel):
    type: Literal["user", "model", "system"]
    text: str


class ToolCall(BaseModel):
    name: str
    arguments: dict


class LLMResponse(BaseModel):
    type: Literal["tool_call", "final"]
    content: Message
    tool_call: ToolCall | None = None
    tokens_used: int = 0  #mock count 

RunStatus = Literal["completed", "max_iterations_exceeded", "budget_exceeded"]

class RunResult(BaseModel):
    status: RunStatus
    output: str | None = None
    iterations_used: int = 0
    tokens_used: int = 0

"""
class MockLLM(LLM):
    def generate(self, messages: list[Message]) -> LLMResponse:
        ...
"""

class LLM(ABC):

    @abstractmethod
    async def generate(self, message: list[Message]) -> LLMResponse:
        pass


class Tool(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass
    
    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> str:
        pass
    
