# src/tools/get_time.py
from datetime import datetime, timezone
from typing import Any
from src.model import Tool


class GetTimeTool(Tool):
    @property
    def name(self) -> str:
        return "get_time"

    @property
    def description(self) -> str:
        return "Returns the current UTC date and time in ISO 8601 format."

    async def execute(self, arguments: dict[str, Any]) -> str:
        return datetime.now(timezone.utc).isoformat()