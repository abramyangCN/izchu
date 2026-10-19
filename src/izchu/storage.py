import json
import os
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any


class JsonStore:
    """Small atomic JSON store for private OAuth state and tokens."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def read(self) -> dict[str, Any] | None:
        with self._lock:
            if not self.path.exists():
                return None
            return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._lock:
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
            )
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(value, handle, ensure_ascii=False, indent=2, default=str)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                temporary_path.chmod(0o600)
                temporary_path.replace(self.path)
            finally:
                temporary_path.unlink(missing_ok=True)

    def delete(self) -> None:
        with self._lock:
            self.path.unlink(missing_ok=True)

