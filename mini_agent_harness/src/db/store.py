# src/store.py
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


class EventStore:
    def __init__(self, db_path: str = "runs.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    #migration
    def _init_db(self):
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                user_input TEXT NOT NULL,
                output TEXT,
                iterations_used INTEGER DEFAULT 0,
                tokens_used INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
        """)
        conn.commit()
        conn.close()

    #create_run
    def create_run(self, user_input: str ,  status: str = "queued") -> str:
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        conn.execute(
            "INSERT INTO runs (id, status, user_input, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, status, user_input, now, now),
        )
        conn.commit()
        conn.close()
        self.append_event(run_id, "run_created", {"user_input": user_input})
        return run_id
    
    #append event
    def append_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        conn = self._connect()
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 FROM events WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO events (run_id, seq, event_type, payload, timestamp) VALUES (?, ?, ?, ?, ?)",
            (run_id, seq, event_type, json.dumps(payload), datetime.now(timezone.utc).isoformat()),
        )
        conn.execute("UPDATE runs SET updated_at = ? WHERE id = ?",
                     (datetime.now(timezone.utc).isoformat(), run_id))
        conn.commit()
        conn.close()
        
    #list of events
    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT seq, event_type, payload, timestamp FROM events WHERE run_id = ? ORDER BY seq",
            (run_id,),
        ).fetchall()
        conn.close()
        return [
            {
                "seq": r["seq"],
                "event_type": r["event_type"],
                "payload": json.loads(r["payload"]),
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_run_status(
        self, run_id: str, status: str, output: str | None = None,
        iterations_used: int | None = None, tokens_used: int | None = None,
    ) -> None:
        conn = self._connect()
        fields = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, datetime.now(timezone.utc).isoformat()]
        if output is not None:
            fields.append("output = ?")
            values.append(output)
        if iterations_used is not None:
            fields.append("iterations_used = ?")
            values.append(iterations_used)
        if tokens_used is not None:
            fields.append("tokens_used = ?")
            values.append(tokens_used)
        values.append(run_id)
        conn.execute(f"UPDATE runs SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        conn.close()

    def list_incomplete_runs(self) -> list[str]:
        conn = self._connect()
        rows = conn.execute("SELECT id FROM runs WHERE status IN ('running', 'queued')").fetchall()
        conn.close()
        return [r["id"] for r in rows]
    
    