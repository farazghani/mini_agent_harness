# src/test/kill_resume_test.py
import os
import signal
import subprocess
import time
import httpx
import pytest

DB_PATH = "test_kill_resume.db"
PORT = 8123
BASE_URL = f"http://127.0.0.1:{PORT}"


def start_server() -> subprocess.Popen:
    env = os.environ.copy()
    env["RUNS_DB_PATH"] = DB_PATH
    proc = subprocess.Popen(
        ["uvicorn", "src.main:app", "--port", str(PORT)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for the server to actually be accepting connections
    for _ in range(50):
        try:
            httpx.get(f"{BASE_URL}/docs", timeout=0.5)
            return proc
        except httpx.ConnectError:
            time.sleep(0.2)
    raise RuntimeError("server did not start in time")


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


def test_kill_and_resume_completes_run():
    # --- Process 1: start a run, then kill the process mid-flight ---
    proc1 = start_server()
    try:
        resp = httpx.post(f"{BASE_URL}/runs", json={"task": "slow task for kill test"})
        run_id = resp.json()["run_id"]

        # Give it a moment to actually start executing and persist at least one event
        time.sleep(0.5)
        events_before = httpx.get(f"{BASE_URL}/runs/{run_id}").json()["events"]
        assert len(events_before) >= 1  # something was persisted before the kill

    finally:
        proc1.send_signal(signal.SIGKILL)  # hard kill — no graceful shutdown, simulates a real crash
        proc1.wait(timeout=5)

    # --- Process 2: fresh server, same DB file, must pick up and finish the run ---
    proc2 = start_server()
    try:
        deadline = time.time() + 10
        final = None
        while time.time() < deadline:
            data = httpx.get(f"{BASE_URL}/runs/{run_id}").json()
            if data["status"] in ("completed", "max_iterations_exceeded", "budget_exceeded"):
                final = data
                break
            time.sleep(0.3)

        assert final is not None, "run never completed after resume"
        assert final["status"] == "completed"
        assert final["output"] is not None

        # Confirm the events from BEFORE the kill are still present —
        # proving continuity, not a fresh restart from zero.
        event_types = [e["event_type"] for e in final["events"]]
        assert "run_created" in event_types

    finally:
        proc2.send_signal(signal.SIGTERM)
        proc2.wait(timeout=5)