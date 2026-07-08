"""Knowledge Graph Sync and Decay Scheduler — Phase K13.

Runs a background thread daemon to periodically synchronize Semantic Memory,
World Model, and Episodic Memory into the Knowledge Graph, and applies temporal
confidence decay to unrefreshed nodes.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from backend.core.config import load_config
from backend.core.logger import log_event
from backend.core.graph import _get_kg

logger = logging.getLogger(__name__)


class KGSyncScheduler:
    """Daemon scheduler for periodic Knowledge Graph sync and temporal decay."""

    _instance: Optional[KGSyncScheduler] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self, interval_seconds: float = 300.0, decay_rate: float = 1.15e-6) -> None:
        if hasattr(self, "_initialized"):
            return
        self.interval_seconds = interval_seconds
        self.decay_rate = decay_rate
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._run_lock = threading.Lock()
        self._initialized = True

    def start(self) -> None:
        """Start the background sync scheduler daemon."""
        with self._run_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="kg-sync-scheduler-daemon",
                daemon=True
            )
            self._thread.start()
            log_event("kg_scheduler_started", f"KG Sync Scheduler started (interval={self.interval_seconds}s)")

    def stop(self) -> None:
        """Stop the background sync scheduler daemon gracefully."""
        with self._run_lock:
            if self._thread is None:
                return
            self._stop_event.set()
            self._thread.join(timeout=5.0)
            self._thread = None
            log_event("kg_scheduler_stopped", "KG Sync Scheduler stopped")

    def trigger_sync(self) -> None:
        """Trigger an immediate sync and decay run synchronously."""
        logger.info("KG Sync Scheduler: Manual sync triggered")
        self._run_tick()

    def _loop(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            self._run_tick()

    def _run_tick(self) -> None:
        """Run a single tick: cross-layer sync + temporal decay."""
        log_event("kg_scheduler_tick_start", "Running KG scheduler synchronization and decay cycle")
        kg = _get_kg()
        if kg is None:
            logger.warning("KG Sync Scheduler: KnowledgeGraph singleton is not available")
            return

        config = load_config()
        db_path = str(config.sqlite_path)

        # 1. Cross-layer synchronization
        try:
            stats = kg.full_sync(
                semantic_db=db_path,
                world_db=db_path,
                episodic_db=db_path
            )
            log_event("kg_scheduler_sync_complete", f"KG sync completed: {stats}")
        except Exception as e:
            log_event("kg_scheduler_sync_error", f"Error during KG sync: {e}")

        # 2. Temporal confidence decay
        try:
            decayed = kg.decay_unrefreshed_nodes(decay_rate=self.decay_rate)
            log_event("kg_scheduler_decay_complete", f"KG temporal decay completed: updated {decayed} nodes")
        except Exception as e:
            log_event("kg_scheduler_decay_error", f"Error during KG decay: {e}")


def start_kg_scheduler(interval_seconds: float = 300.0, decay_rate: float = 1.15e-6) -> KGSyncScheduler:
    """Start the global KG sync scheduler singleton."""
    scheduler = KGSyncScheduler(interval_seconds=interval_seconds, decay_rate=decay_rate)
    scheduler.start()
    return scheduler


def stop_kg_scheduler() -> None:
    """Stop the global KG sync scheduler singleton."""
    scheduler = KGSyncScheduler()
    scheduler.stop()
