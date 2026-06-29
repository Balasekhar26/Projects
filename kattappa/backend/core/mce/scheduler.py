"""MCE Component 7b: Scheduler.

Runs MCEConsolidationEngine.run_cycle() as a background daemon thread
at a configurable interval (default: every 6 hours).
Persists cycle state to a JSON file for recovery across restarts.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from backend.core.config import load_config
from backend.core.logger import log_event
from backend.core.mce.consolidation_engine import ConsolidationReport, MCEConsolidationEngine

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_HOURS: float = 6.0


def _state_path() -> Path:
    config = load_config()
    return config.sqlite_path.parent / "mce_scheduler_state.json"


class MCEScheduler:
    """Background daemon that fires consolidation cycles at a fixed interval."""

    _instance: Optional["MCEScheduler"] = None
    _lock = threading.Lock()

    def __init__(self, interval_hours: float = _DEFAULT_INTERVAL_HOURS):
        self.interval_sec = interval_hours * 3600.0
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_report: Optional[Dict[str, Any]] = None
        self._cycle_count: int = 0
        self._next_run_at: float = time.time()  # run immediately on first startup

        # Restore state from disk if available
        self._load_state()

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls, interval_hours: float = _DEFAULT_INTERVAL_HOURS) -> "MCEScheduler":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(interval_hours=interval_hours)
            return cls._instance

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background scheduler thread if not already running."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="MCESchedulerDaemon",
            daemon=True,
        )
        self._thread.start()
        log_event("mce_scheduler_started", f"MCEScheduler started (interval={self.interval_sec / 3600:.1f}h)")

    def stop(self) -> None:
        """Signal the background thread to stop."""
        self._stop_event.set()
        log_event("mce_scheduler_stopped", "MCEScheduler stop requested")

    def trigger_now(self) -> ConsolidationReport:
        """Manually trigger an immediate cycle (blocking)."""
        log_event("mce_scheduler_manual_trigger", "Manual consolidation cycle triggered")
        report = MCEConsolidationEngine.run_cycle()
        self._cycle_count += 1
        self._last_report = report.to_dict()
        self._next_run_at = time.time() + self.interval_sec
        self._save_state()
        return report

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            if now >= self._next_run_at:
                try:
                    report = MCEConsolidationEngine.run_cycle()
                    self._cycle_count += 1
                    self._last_report = report.to_dict()
                    self._next_run_at = time.time() + self.interval_sec
                    self._save_state()
                except Exception as exc:
                    logger.error("MCEScheduler cycle error: %s", exc)
                    self._next_run_at = time.time() + 300.0  # retry in 5 min on error

            # Sleep in small increments so stop_event is checked promptly
            self._stop_event.wait(timeout=60.0)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._thread is not None and self._thread.is_alive(),
            "cycle_count": self._cycle_count,
            "interval_hours": self.interval_sec / 3600.0,
            "next_run_at": self._next_run_at,
            "last_report": self._last_report,
        }

    def _save_state(self) -> None:
        try:
            path = _state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({
                    "cycle_count": self._cycle_count,
                    "next_run_at": self._next_run_at,
                    "last_report": self._last_report,
                }, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("MCEScheduler: could not save state: %s", exc)

    def _load_state(self) -> None:
        try:
            path = _state_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                self._cycle_count = int(data.get("cycle_count", 0))
                self._next_run_at = float(data.get("next_run_at", time.time()))
                self._last_report = data.get("last_report")
        except Exception as exc:
            logger.warning("MCEScheduler: could not load state: %s", exc)
