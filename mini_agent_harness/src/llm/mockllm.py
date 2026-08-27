from src.model import LLM , LLMResponse , Message

class MockLLM(LLM):
    def __init__(self, response: list[LLMResponse] | None = None):
        self.responses = response or []
        self.calls: list[list[Message]] = []
        


    async def generate(self, message: list[Message]) -> LLMResponse:
        self.calls.append(list(message))
        if self.responses:
            return self.responses.pop(0)
        return LLMResponse(
            type="final",
            content=Message(type="model", text="hello")
        )
       
        

        

        
        

