from __future__ import annotations
import threading
from typing import Callable, Any

class MessageBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        with self._lock:
            if topic not in self._listeners:
                self._listeners[topic] = []
            self._listeners[topic].append(callback)

    def publish(self, topic: str, data: Any) -> None:
        with self._lock:
            listeners = list(self._listeners.get(topic, []))
        for listener in listeners:
            try:
                listener(data)
            except Exception:
                pass
