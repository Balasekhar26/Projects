"""Checkpoint Recovery Engine (Program 32.0).

Serializes active plan execution states, task step progression counters,
and environment variable bindings to support persistent workflow resumption.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from backend.core.config import runtime_data_root


def _checkpoint_dir() -> Path:
    p = runtime_data_root() / "backend" / "data" / "planning"
    p.mkdir(parents=True, exist_ok=True)
    return p


class CheckpointRecovery:
    """Manages active plan parameter backups and persistence files."""

    _lock = threading.RLock()

    def __init__(self, storage_dir: Optional[str | Path] = None) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else _checkpoint_dir()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = self.storage_dir / "plan_checkpoints.json"

    def _load_db(self) -> Dict[str, Any]:
        if not self.checkpoint_file.exists():
            return {"checkpoints": {}}
        try:
            with self.checkpoint_file.open(encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            return {"checkpoints": {}}

    def _save_db(self, db: Dict[str, Any]) -> None:
        with self.checkpoint_file.open("w", encoding="utf-8") as fh:
            json.dump(db, fh, indent=2)

    # ── APIs ──────────────────────────────────────────────────────────────────

    def save_checkpoint(
        self,
        plan_id: str,
        step_index: int,
        variables: Dict[str, Any],
    ) -> str:
        """Saves active plan progress parameters. Returns unique checkpoint ID."""
        with self._lock:
            db = self._load_db()
            ckpt_id = f"ckpt_{uuid.uuid4().hex[:8]}"
            db["checkpoints"][ckpt_id] = {
                "checkpoint_id": ckpt_id,
                "plan_id": plan_id,
                "step_index": step_index,
                "variables": dict(variables),
                "timestamp": time.time(),
            }
            self._save_db(db)
            return ckpt_id

    def load_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Loads and returns saved checkpoint parameters."""
        with self._lock:
            db = self._load_db()
            return db["checkpoints"].get(checkpoint_id)

    def clear_checkpoint(self, checkpoint_id: str) -> None:
        """Deletes checkpoint record upon successful plan resolution."""
        with self._lock:
            db = self._load_db()
            if checkpoint_id in db["checkpoints"]:
                del db["checkpoints"][checkpoint_id]
                self._save_db(db)
