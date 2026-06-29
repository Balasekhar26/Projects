"""Cognitive Blackboard — Phase K10.5.

Decouples agent and subsystem communication. Rather than point-to-point calls,
components post observations, insights, hypotheses, and state changes to a
shared global blackboard, allowing other subsystems to react asynchronously.
"""
from __future__ import annotations

import enum
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


# ---------------------------------------------------------------------------
# High-level Blackboard API (used by graph.py and cognitive pipeline)
# ---------------------------------------------------------------------------

class EntryKind(enum.Enum):
    """Semantic category of a blackboard workspace entry."""
    FACT = "fact"
    ASSUMPTION = "assumption"
    CONSTRAINT = "constraint"
    AGENT_OUTPUT = "agent_output"


@dataclass
class BlackboardEntry:
    """A single typed entry in a session-scoped Blackboard workspace."""
    entry_id: str
    key: str
    value: Any
    kind: EntryKind
    timestamp: float = field(default_factory=time.time)

    @property
    def source(self) -> str:
        return self.key

    @property
    def content(self) -> Any:
        return self.value


@dataclass
class SharedContext:
    """Immutable context attached to a Blackboard workspace session."""
    session_id: str
    user_intent: str
    working_memory: Any = None


class Blackboard:
    """Session-scoped cognitive workspace used by the LangGraph pipeline.

    Provides typed entry methods (add_fact, add_assumption, add_constraint,
    add_agent_output) and a unified entries() iterator so that downstream
    nodes can inspect the accumulated workspace state.
    """

    def __init__(self, context: SharedContext) -> None:
        self.context = context
        self._entries: List[BlackboardEntry] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def add_fact(self, key: str, value: Any) -> BlackboardEntry:
        """Record a verified fact (high confidence, read-only claim)."""
        return self._add(key, value, EntryKind.FACT)

    def add_assumption(self, key: str, value: Any) -> BlackboardEntry:
        """Record a tentative assumption (may be revised)."""
        return self._add(key, value, EntryKind.ASSUMPTION)

    def add_constraint(self, key: str, value: Any) -> BlackboardEntry:
        """Record a hard constraint or policy violation."""
        return self._add(key, value, EntryKind.CONSTRAINT)

    def add_agent_output(self, key: str, value: Any) -> BlackboardEntry:
        """Record structured output produced by an agent node."""
        return self._add(key, value, EntryKind.AGENT_OUTPUT)

    def _add(self, key: str, value: Any, kind: EntryKind) -> BlackboardEntry:
        entry = BlackboardEntry(
            entry_id=str(uuid.uuid4()),
            key=key,
            value=value,
            kind=kind,
        )
        with self._lock:
            self._entries.append(entry)
        log_event("blackboard_entry", f"[{kind.value}] {key}")
        return entry

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def entries(self, kind: Optional[EntryKind] = None) -> List[BlackboardEntry]:
        """Return all entries, optionally filtered by kind."""
        with self._lock:
            if kind is None:
                return list(self._entries)
            return [e for e in self._entries if e.kind == kind]

    def get(self, key: str) -> Optional[BlackboardEntry]:
        """Return the most recent entry matching *key*, or None."""
        with self._lock:
            for entry in reversed(self._entries):
                if entry.key == key:
                    return entry
        return None

    def by_source(self, source: str) -> List[BlackboardEntry]:
        """Return all entries matching the given source (key)."""
        with self._lock:
            return [e for e in self._entries if e.source == source]
        return None

    def clear(self) -> None:
        """Reset the workspace (primarily for tests)."""
        with self._lock:
            self._entries.clear()

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema
        return core_schema.json_or_python_schema(
            json_schema=core_schema.any_schema(),
            python_schema=core_schema.is_instance_schema(cls),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: {
                    "session_id": instance.context.session_id if hasattr(instance.context, "session_id") else str(instance.context),
                    "entries": [
                        {
                            "entry_id": e.entry_id,
                            "key": e.key,
                            "value": e.value,
                            "kind": e.kind.value,
                            "timestamp": e.timestamp,
                        }
                        for e in instance.entries()
                    ]
                }
            )
        )

