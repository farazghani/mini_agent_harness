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


## defining models 
- 


##  choose abstract class method to define LLM interface
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

- added mock llm with response made test and ran arguments working fine

- 

# TOOLS: Adding tools
- build a bastract class to define tools makes it more maintainable and added registry to define tools 

- added {calculator} tool
-  decided to use ast parses the math expression into a safe, structured tree so we can check each operation is allowed before computing it, instead of using eval() which would execute arbitrary/malicious code. 
 was confused initially here normal approach i tried ws parse argument and extract function via regex but ai suggest ast

- Path (pathlib) instead of raw strings — because it gives .resolve() (collapses ../symlinks into the real final location) and .relative_to() (checks containment reliably), which plain string concatenation/comparison can't do safely.
Reject absolute paths upfront, no legitimate request needs one; blocks /etc/passwd-style input immediately.
.resolve() before checking:  ensures we're validating the real destination, not the raw ../../ text, so traversal tricks can't slip through.
relative_to(base_dir) — the actual sandbox check: confirms the resolved path is truly inside base_dir, not just string-prefixed with it (which is spoofable, e.g. /sandbox2 vs /sandbox).
Check .exists() / .is_file() separately — a safe path might still not exist or might be a directory; keeps error messages precise instead of a raw exception.
Return error strings, never raise — matches the Tool contract, so the agent loop and LLM can see and react to failures instead of crashing.
// used help here was unfamiliar with path library


## agentloop

- Built an Agent.run loop that feeds the LLM the full growing history each iteration, dispatches tool_call responses to the real ToolRegistry/tools, appends results back to history, and stops on "final" or after max_iterations; tested it with a scripted MockLLM (final-only, tool-call-then-final, unknown tool, malformed tool_call, max-iterations-exhausted)

- ERROR FIX : fixed a bug where MockLLM.calls stored references to the same mutating history list instead of snapshots, making all recorded calls show the final history state (fixed via list(messages) copy on append).

- phase 1 complete :  remaining job backend call post /run

# phase 2: Limits and Failure Handling 


## update on models: 
 - added token_used in run result here because thats how llm   calls return token good way of keeping record 
   suppose if we have to find token limit we can just calculate all the tokens in list[message] from history and if it exceeds shut the process down

- add another model Runresult:
    with attributes such as runstatus a literal that can be from running , completed , max_iterations_achieved , succesfully_completed , token_budget_exceeded

## update on agent loop
 - previous iteration , def run use to return str added the structured output run_result here 

- added the check tokens_used > self.max_tokens for token limits 
- added execute_tool with retry for failed state logic 

## missing 
- havent added updated tests on it yet 
# phase 3 : building memory layer     

- to maintain state and resumability the obvious decision would be to add a db layer 
- using sqllite3 (better than json help us in atomic updates as well)

## building db/store.py 
- decided on 2 schemas 1st is RUN (id , status , user_input  , output  , iterations_used , tokens_used , created_at , updated_At)
- EVENT(id , run_id , seq , event_type , payload , timestamp)

- create_run(): to create a new run as well as appended event
- get_events(): to return events format : list[dict[str , any]]
- get_run(): to get all existing runs 
- update_run_status(): to update the status of the selected run
- list_incomplete_runs(): list all runs under running

## updating agent loop 
- require major updates here before status we were dependent on runtime memory for storing now , we require to update and maintain our memory with runtime 
- creating start() to create a new run and _execute()
- resume() for runs that have already a status == "running" ignores others and resumes the run from last step 
-  get_history() does three things populate history: list[message] calc tokens and stores no. of iterations done if tool call
- excute: 
  implement get history of run if not exist then use initial history = [] , token_count = 0 and iteration = 0
- execute with retry logic : 
  implement with retry logic inside execute only when type = tool_Call and tool_call is none
 // took help here as was confused on the logic 

##  phase 4 : Streaming and backend
- 


                            
                                 
