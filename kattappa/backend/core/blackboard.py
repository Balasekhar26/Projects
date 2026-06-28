"""Cognitive Blackboard — Phase K10.5.

Decouples agent and subsystem communication. Rather than point-to-point calls,
components post observations, insights, hypotheses, and state changes to a
shared global blackboard, allowing other subsystems to react asynchronously.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from backend.core.logger import log_event


@dataclass(frozen=True)
class BlackboardPost:
    post_id: str
    publisher: str
    topic: str
    payload: Dict[str, Any]
    confidence: float
    timestamp: float
    referenced_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "post_id": self.post_id,
            "publisher": self.publisher,
            "topic": self.topic,
            "payload": self.payload,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "referenced_ids": list(self.referenced_ids),
        }


class CognitiveBlackboard:
    """Thread-safe global Blackboard for decoupled cognitive routing."""

    _instance: Optional[CognitiveBlackboard] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> CognitiveBlackboard:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Initialize instance variables safely (called once because of __new__ guard)
        if not hasattr(self, "_initialized"):
            self._posts: List[BlackboardPost] = []
            self._subscriptions: Dict[str, List[Callable[[BlackboardPost], None]]] = {}
            self._rw_lock = threading.RLock()
            self._initialized = True

    def publish(
        self,
        publisher: str,
        topic: str,
        payload: Dict[str, Any],
        confidence: float = 1.0,
        referenced_ids: List[str] | tuple[str, ...] | None = None,
    ) -> BlackboardPost:
        """Publish a post to the blackboard and notify active subscribers.

        Parameters
        ----------
        publisher : str
            The name of the publishing component/agent.
        topic : str
            The topic category (e.g. "observation", "hypothesis", "insight").
        payload : Dict[str, Any]
            The custom payload dictionary.
        confidence : float
            Publisher confidence level (0.0 to 1.0).
        referenced_ids : List[str] | None
            IDs of other blackboard posts referenced by this post (lineage).
        """
        ref_ids = tuple(referenced_ids) if referenced_ids else ()
        post = BlackboardPost(
            post_id=str(uuid.uuid4()),
            publisher=publisher,
            topic=topic,
            payload=payload,
            confidence=confidence,
            timestamp=time.time(),
            referenced_ids=ref_ids,
        )

        with self._rw_lock:
            self._posts.append(post)
            # Find matching subscribers (supports exact match and wildcard '*')
            callbacks = []
            for sub_topic, cb_list in self._subscriptions.items():
                if sub_topic == topic or sub_topic == "*":
                    callbacks.extend(cb_list)

        # Notify subscribers outside the read-write lock to avoid deadlock
        for callback in callbacks:
            try:
                callback(post)
            except Exception as e:
                log_event("blackboard_subscriber_error", f"Callback on topic {topic} failed: {e}")

        log_event("blackboard_publish", f"Topic: {topic} | Publisher: {publisher} | ID: {post.post_id}")
        return post

    def subscribe(self, topic: str, callback: Callable[[BlackboardPost], None]) -> None:
        """Subscribe to a specific topic or '*' for all topics."""
        with self._rw_lock:
            if topic not in self._subscriptions:
                self._subscriptions[topic] = []
            self._subscriptions[topic].append(callback)
            log_event("blackboard_subscribe", f"New subscriber added for topic: {topic}")

    def unsubscribe(self, topic: str, callback: Callable[[BlackboardPost], None]) -> bool:
        """Remove a subscription callback."""
        with self._rw_lock:
            if topic in self._subscriptions and callback in self._subscriptions[topic]:
                self._subscriptions[topic].remove(callback)
                return True
            return False

    def get_history(
        self,
        topic: Optional[str] = None,
        publisher: Optional[str] = None,
        limit: int = 100,
    ) -> List[BlackboardPost]:
        """Fetch matching posts sorted descending by timestamp (newest first)."""
        with self._rw_lock:
            filtered = self._posts
            if topic is not None:
                filtered = [p for p in filtered if p.topic == topic]
            if publisher is not None:
                filtered = [p for p in filtered if p.publisher == publisher]
            
            # Sort newest first
            sorted_posts = sorted(filtered, key=lambda p: p.timestamp, reverse=True)
            return sorted_posts[:limit]

    def clear(self) -> None:
        """Reset all posts and subscriptions (primarily for tests)."""
        with self._rw_lock:
            self._posts.clear()
            self._subscriptions.clear()
            log_event("blackboard_clear", "Blackboard cleared.")


# Global instance
BLACKBOARD = CognitiveBlackboard()
