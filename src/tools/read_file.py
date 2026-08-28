# src/tools/read_file.py
from pathlib import Path
from typing import Any
from src.model import Tool


class ReadFileTool(Tool):
    """Reads a file's contents, sandboxed to a fixed working directory."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir).resolve()

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Reads the contents of a text file within the sandboxed working directory."

    def _resolve_safe_path(self, path: str) -> Path:
        # Reject absolute paths outright — they're always suspicious here,
        # since everything should be relative to base_dir.
        requested = Path(path)
        if requested.is_absolute():
            raise ValueError("Absolute paths are not allowed")

        # Join with base_dir, then resolve to collapse any ".." segments,
        # symlinks, etc. into a final canonical absolute path.
        candidate = (self.base_dir / requested).resolve()

        # The real check: is candidate actually inside base_dir?
        # This works regardless of how many "../" tricks were used to get there.
        try:
            candidate.relative_to(self.base_dir)
        except ValueError:
            raise ValueError("Path escapes the sandboxed working directory")

        return candidate

    async def execute(self, arguments: dict[str, Any]) -> str:
        path = arguments.get("path")
        if not path:
            return "Error: 'path' argument is required"

        try:
            safe_path = self._resolve_safe_path(path)
        except ValueError as e:
            return f"Error: {e}"

        if not safe_path.exists():
            return f"Error: file not found: {path}"
        if not safe_path.is_file():
            return f"Error: not a file: {path}"

        try:
            return safe_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "Error: file is not valid UTF-8 text"
        except OSError as e:
            return f"Error: could not read file — {e}"