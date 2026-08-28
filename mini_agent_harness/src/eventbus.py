# src/eventbus.py
import asyncio
from src.db.store import EventStore

class EventBus:
    """In-memory pub/sub, purely for pushing live updates to open SSE connections.
    Not the source of truth — SQLite (EventStore) is. If no one's listening,
    published events are simply dropped; nothing is lost, since they're
    already persisted separately."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(run_id, []).append(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(run_id, [])
        if q in subs:
            subs.remove(q)

    def publish(self, run_id: str, event: dict) -> None:
        for q in self._subscribers.get(run_id, []):
            q.put_nowait(event)


class PublishingEventStore:
    """Same interface Agent already uses (append_event, get_events, etc.) —
    Agent doesn't know or care this exists; it just calls self.store.append_event(...)
    like before. This wrapper persists to SQLite AND pushes to any live SSE subscribers."""

    def __init__(self, store: EventStore, bus: EventBus):
        self.store = store
        self.bus = bus

    def create_run(self, user_input: str, status: str = "queued") -> str:
        return self.store.create_run(user_input, status)

    def append_event(self, run_id: str, event_type: str, payload: dict) -> None:
        self.store.append_event(run_id, event_type, payload)
        self.bus.publish(run_id, {"event_type": event_type, "payload": payload})

    def update_run_status(self, run_id: str, status: str, **kwargs) -> None:
        self.store.update_run_status(run_id, status, **kwargs)
        self.bus.publish(run_id, {"event_type": "status_change", "payload": {"status": status}})

    def get_events(self, run_id: str) -> list[dict]:
        return self.store.get_events(run_id)

    def get_run(self, run_id: str) -> dict | None:
        return self.store.get_run(run_id)

    def list_incomplete_runs(self) -> list[str]:
        return self.store.list_incomplete_runs()
    
