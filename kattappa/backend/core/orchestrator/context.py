from __future__ import annotations
import threading
import copy
from typing import Any

class SharedContext:
    def __init__(self, initial_data: dict[str, Any] | None = None):
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        if initial_data:
            self._data.update(initial_data)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def update(self, other_dict: dict[str, Any]) -> None:
        with self._lock:
            self._data.update(other_dict)

    def pop(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.pop(key, default)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)
