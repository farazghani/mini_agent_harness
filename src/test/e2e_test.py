# src/test/e2e_test.py
import os
import time
import tempfile
import pytest
from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def client():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)  # let EventStore create schema fresh on first use
    app = create_app(db_path=db_path)
    with TestClient(app) as c:   # `with` triggers startup lifespan event
        yield c
    if os.path.exists(db_path):
        os.remove(db_path)


def wait_for_status(client, run_id: str, target_statuses: set[str], timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/runs/{run_id}")
        data = resp.json()
        if data["status"] in target_statuses:
            return data
        time.sleep(0.1)
    raise TimeoutError(f"run {run_id} did not reach {target_statuses} in time")


def test_successful_run_completes(client):
    resp = client.post("/runs", json={"task": "what is 6 times 7?"})
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body
    assert body["status"] == "queued"

    final = wait_for_status(client, body["run_id"], {"completed", "max_iterations_exceeded", "budget_exceeded", "failed"})
    assert final["status"] == "completed", final
    assert final["output"] is not None
    assert len(final["events"]) >= 2


def test_get_unknown_run_returns_404(client):
    resp = client.get("/runs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_stream_endpoint_returns_events(client):
    resp = client.post("/runs", json={"task": "quick task"})
    run_id = resp.json()["run_id"]
    wait_for_status(client, run_id, {"completed", "max_iterations_exceeded", "budget_exceeded", "failed"})

    with client.stream("GET", f"/runs/{run_id}/stream") as stream_resp:
        assert stream_resp.status_code == 200
        lines = [line for line in stream_resp.iter_lines() if line.startswith("data:")]

    assert len(lines) >= 2
    assert any('"event_type": "run_created"' in line for line in lines)


def test_concurrency_cap_queues_extra_runs(client):
    run_ids = [client.post("/runs", json={"task": f"task {i}"}).json()["run_id"] for i in range(5)]
    for rid in run_ids:
        wait_for_status(client, rid, {"completed", "max_iterations_exceeded", "budget_exceeded", "failed"})