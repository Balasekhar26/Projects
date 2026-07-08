"""Mission Ledger Database (Program 24.0).

Provides persistent logging for long-horizon mission execution steps, checkpoint histories, and outcomes.
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


def _ledger_file_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "mission_ledger.json"


class MissionLedger:
    """Registry capturing mission steps, compensation tracks, and planner choices."""

    _lock = threading.RLock()

    @classmethod
    def load_ledger(cls) -> List[Dict[str, Any]]:
        with cls._lock:
            path = _ledger_file_path()
            if not path.exists():
                return []
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []

    @classmethod
    def save_ledger(cls, logs: List[Dict[str, Any]]) -> None:
        with cls._lock:
            path = _ledger_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(logs, indent=2), encoding="utf-8")

    @classmethod
    def record_decision(
        cls,
        mission_id: str,
        stage: str,
        decision: str,
        rationale: str,
        status: str = "COMPLETED"
    ) -> Dict[str, Any]:
        """Logs a planner decision and reasoning to the ledger list."""
        with cls._lock:
            ledger = cls.load_ledger()
            log_id = f"led_{int(time.time())}_{len(ledger)}"
            log_entry = {
                "log_id": log_id,
                "mission_id": mission_id,
                "timestamp": time.time(),
                "stage": stage,
                "decision": decision,
                "rationale": rationale,
                "status": status
            }
            ledger.append(log_entry)
            cls.save_ledger(ledger)
            logger.info("MissionLedger: Logged decision %s for mission %s", log_id, mission_id)
            return log_entry

    @classmethod
    def get_mission_history(cls, mission_id: str) -> List[Dict[str, Any]]:
        with cls._lock:
            return [log for log in cls.load_ledger() if log["mission_id"] == mission_id]

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls.save_ledger([])
