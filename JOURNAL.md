## mini-agnent - harness



 ## core decisions 
 - lang: [python.311]
 - virtual env package - [uv]
 

# phase 1 (agent)

- starting with the main agent loop had decided on few kew decisions -> phase planning 
 - message: type ,str
 -  llmresponse: type , content: message 
 - toolcall : name , arguments
 -  mainloop call - generate(message) ->  llmresponse


## expected outcome of this section
   agent : llm call -> tool call -> if output : final ? return : toolcall->     max_iterations


##  decision1 : choose abstract class method to define LLM interface
-  becasue Every LLM used by my agent must provide a call() method with this behavior.
- class MockLLM(LLM):
    def call(...):

- class OpenAILLM(LLM):
    def call(...):


```
                  ┌───────────────┐
                  │  Agent Loop   │
                  └───────┬───────┘
                          │
                          │ depends on
                          ▼
                  ┌───────────────┐
                  │     LLM       │
                  │   interface   │
                  └───────┬───────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
        ┌───────────┐           ┌────────────┐
        │ MockLLM   │           │ Real LLM   │
        └───────────┘           └────────────┘

```



                                                
                            
                                 
