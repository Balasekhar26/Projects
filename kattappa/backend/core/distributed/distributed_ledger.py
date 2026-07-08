"""Distributed Ledger Database (Program 25.0).

Maintains persistent audits of cluster node assignments, tasks migrations, and workers failures.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from backend.core.config import runtime_data_root

logger = logging.getLogger(__name__)


def _ledger_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "distributed_ledger.json"


class DistributedLedger:
    """Stores cluster transaction histories for verification and replay simulations."""

    _lock = threading.RLock()

    @classmethod
    def load_ledger(cls) -> List[Dict[str, Any]]:
        with cls._lock:
            path = _ledger_path()
            if not path.exists():
                return []
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []

    @classmethod
    def save_ledger(cls, logs: List[Dict[str, Any]]) -> None:
        with cls._lock:
            path = _ledger_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(logs, indent=2), encoding="utf-8")

    @classmethod
    def log_assignment(
        cls,
        task_id: str,
        node_id: str,
        action: str,
        status: str = "assigned"
    ) -> Dict[str, Any]:
        """Logs a task assignment to a specific worker node."""
        with cls._lock:
            ledger = cls.load_ledger()
            entry = {
                "assignment_id": f"asg_{int(time.time())}_{len(ledger)}",
                "task_id": task_id,
                "node_id": node_id,
                "action": action,
                "status": status,
                "timestamp": time.time()
            }
            ledger.append(entry)
            cls.save_ledger(ledger)
            logger.info("DistributedLedger: Logged task %s assigned to worker %s", task_id, node_id)
            return entry

    @classmethod
    def log_migration(cls, task_id: str, old_node_id: str, new_node_id: str, reason: str) -> None:
        """Logs a task migration event (failover re-routing)."""
        with cls._lock:
            ledger = cls.load_ledger()
            entry = {
                "assignment_id": f"mig_{int(time.time())}_{len(ledger)}",
                "task_id": task_id,
                "old_node_id": old_node_id,
                "new_node_id": new_node_id,
                "status": "migrated",
                "reason": reason,
                "timestamp": time.time()
            }
            ledger.append(entry)
            cls.save_ledger(ledger)
            logger.warning("DistributedLedger: Task %s migrated from %s to %s — %s", task_id, old_node_id, new_node_id, reason)

    @classmethod
    def get_task_assignments(cls, task_id: str) -> List[Dict[str, Any]]:
        with cls._lock:
            return [log for log in cls.load_ledger() if log.get("task_id") == task_id]

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls.save_ledger([])
