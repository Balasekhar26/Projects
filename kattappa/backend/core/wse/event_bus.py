"""WSE Component 5: WSEEventBus.

System-wide, ledger-connected publish/subscribe bus.
- publish(event) → appends to SQLiteLedgerStore AND fires topic subscribers
- subscribe(topic, callback) → register a listener per EventType string
- Singleton, thread-safe
- Distinct from governor/event_bus.py (which is private to the governor)
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.core.config import load_config
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.stores.sqlite_store import SQLiteLedgerStore
from backend.core.logger import log_event

logger = logging.getLogger(__name__)

# Type alias for subscriber callbacks
_Callback = Callable[[str, LedgerEvent], None]


def _wse_db_path() -> str:
    config = load_config()
    wse_dir = config.sqlite_path.parent / "wse"
    wse_dir.mkdir(parents=True, exist_ok=True)
    return str(wse_dir / "wse_events.db")


class WSEEventBus:
    """System-wide ledger-connected event bus for Kattappa."""

    _instance: Optional["WSEEventBus"] = None
    _instance_lock = threading.Lock()

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._store = SQLiteLedgerStore(db_path or _wse_db_path())
        self._subscribers: Dict[str, List[_Callback]] = defaultdict(list)
        self._sub_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "WSEEventBus":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls, db_path: Optional[str] = None) -> "WSEEventBus":
        """For testing: replace the singleton with a fresh instance."""
        with cls._instance_lock:
            cls._instance = cls(db_path=db_path)
            return cls._instance

    # ------------------------------------------------------------------
    # Pub/Sub
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, callback: _Callback) -> None:
        """Subscribe to events of a given topic (EventType.value string)."""
        with self._sub_lock:
            if callback not in self._subscribers[topic]:
                self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: _Callback) -> None:
        """Unsubscribe from a topic."""
        with self._sub_lock:
            try:
                self._subscribers[topic].remove(callback)
            except ValueError:
                pass

    def publish(self, event: LedgerEvent) -> None:
        """Persist event to the ledger store, then notify all topic subscribers."""
        # 1. Append to ledger (idempotent — duplicate event_id raises ValueError)
        try:
            self._store.append(event)
        except ValueError:
            logger.debug("WSEEventBus: duplicate event_id=%s skipped", event.event_id)
            return

        log_event(
            "wse_event_published",
            f"event_id={event.event_id} type={event.event_type.value} "
            f"actor={event.actor} subsystem={event.subsystem}",
        )

        # 2. Fire topic subscribers (synchronous; subscriber errors are isolated)
        topic = event.event_type.value
        with self._sub_lock:
            callbacks = list(self._subscribers.get(topic, []))
            # Also fire wildcard subscribers registered under "*"
            callbacks += list(self._subscribers.get("*", []))

        for cb in callbacks:
            try:
                cb(topic, event)
            except Exception as exc:
                logger.error(
                    "WSEEventBus subscriber error [topic=%s, cb=%s]: %s",
                    topic, cb, exc,
                )

    # ------------------------------------------------------------------
    # Store access
    # ------------------------------------------------------------------

    @property
    def store(self) -> SQLiteLedgerStore:
        """Direct access to the underlying ledger store (for Timeline/Diff)."""
        return self._store
