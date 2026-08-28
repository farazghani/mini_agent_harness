# src/main.py
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.run_manager import RunManager

app = FastAPI()
manager = RunManager()


class CreateRunRequest(BaseModel):
    task: str


@app.on_event("startup")
async def on_startup():
    # This is the resumability requirement in action: any run left "running"
    # or "queued" from a previous process that died gets picked back up here.
    await manager.resume_incomplete_runs()


@app.post("/runs")
async def create_run(body: CreateRunRequest):
    if not body.task.strip():
        raise HTTPException(400, "task is required")
    run_id = await manager.start_run(body.task)
    return {"run_id": run_id, "status": "queued"}


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    run = manager.store.get_run(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return {**run, "events": manager.store.get_events(run_id)}


@app.get("/runs/{run_id}/stream")
async def stream_run(run_id: str):
    run = manager.store.get_run(run_id)
    if run is None:
        raise HTTPException(404, "run not found")

    async def event_generator():
        # 1. Replay everything that already happened, so a client connecting
        #    late (or reconnecting) still sees the full history first.
        for event in manager.store.get_events(run_id):
            yield f"data: {json.dumps(event)}\n\n"

        current = manager.store.get_run(run_id)
        if current["status"] not in ("queued", "running"):
            yield f"data: {json.dumps({'event_type': 'run_finished', 'payload': {'status': current['status']}})}\n\n"
            return

        # 2. Then subscribe for live events as they happen.
        queue = manager.bus.subscribe(run_id)
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("event_type") == "status_change" and \
                   event["payload"]["status"] not in ("queued", "running"):
                    break  # run finished — close the stream
        finally:
            manager.bus.unsubscribe(run_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
