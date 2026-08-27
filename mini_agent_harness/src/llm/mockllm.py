from src.model import LLM , LLMResponse , Message

class MockLLM(LLM):
    def __init__(self, response: LLMResponse | None = None):
        self.response = response

    async def generate(self , message : Message) -> LLMResponse:

        if self.response is None:
            return LLMResponse(
                type= "final",
                content= Message(type="model" ,text="hello")
                )
    
        return self.response
       
        

        

        
        

