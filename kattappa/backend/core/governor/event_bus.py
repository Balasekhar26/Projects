import threading
from collections import defaultdict
from typing import Callable, Any, Dict, List

class EventBus:
    """
    A simple thread-safe local event bus for publishing and subscribing to
    resource metrics updates and governor decisions.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EventBus, cls).__new__(cls)
                cls._instance._subscribers = defaultdict(list)
                cls._instance._subscribers_lock = threading.Lock()
        return cls._instance

    def subscribe(self, topic: str, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        Subscribes to updates on a specific topic.
        """
        with self._subscribers_lock:
            if callback not in self._subscribers[topic]:
                self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        Unsubscribes from updates on a specific topic.
        """
        with self._subscribers_lock:
            if callback in self._subscribers[topic]:
                self._subscribers[topic].remove(callback)

    def publish(self, topic: str, data: Dict[str, Any]) -> None:
        """
        Publishes data to all subscribers on the topic.
        """
        with self._subscribers_lock:
            callbacks = list(self._subscribers[topic])
            
        for callback in callbacks:
            try:
                callback(topic, data)
            except Exception:
                # Prevent callback failures from crashing publishers
                pass
