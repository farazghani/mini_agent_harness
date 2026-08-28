# src/main.py
import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.run_manager import RunManager


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI()
    manager = RunManager(db_path=db_path or os.environ.get("RUNS_DB_PATH", "runs.db"))
    app.state.manager = manager

    class CreateRunRequest(BaseModel):
        task: str

    @app.on_event("startup")
    async def on_startup():
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
            for event in manager.store.get_events(run_id):
                yield f"data: {json.dumps(event)}\n\n"

            current = manager.store.get_run(run_id)
            if current["status"] not in ("queued", "running"):
                yield f"data: {json.dumps({'event_type': 'run_finished', 'payload': {'status': current['status']}})}\n\n"
                return

            queue = manager.bus.subscribe(run_id)
            try:
                while True:
                    event = await queue.get()
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("event_type") == "status_change" and \
                       event["payload"]["status"] not in ("queued", "running"):
                        break
            finally:
                manager.bus.unsubscribe(run_id, queue)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return app


# Real server entrypoint — `uvicorn src.main:app`
app = create_app()