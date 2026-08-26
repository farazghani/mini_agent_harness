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

"""

class MockLLM(LLM):
    def generate(self, messages: list[Message]) -> LLMResponse:
        ...
"""

class LLM(ABC):

    @abstractmethod
    def generate(self, message: Message) -> LLMResponse:
        pass



class Tool(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> str:
        pass
x
    
