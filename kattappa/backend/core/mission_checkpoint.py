from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.mission_state import MissionState


def _checkpoint_file_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "mission_checkpoints.json"


class MissionCheckpoint:
    _lock = threading.RLock()

    @classmethod
    def load_checkpoints(cls) -> list[dict[str, Any]]:
        with cls._lock:
            path = _checkpoint_file_path()
            if not path.exists():
                # Seed default checkpoints matching seed mission
                initial = [
                    {
                        "checkpoint_id": "chp_drone_001",
                        "mission_id": "mis_drone_jam",
                        "timestamp": time.time() - 86400,
                        "stage": "Research",
                        "progress": 30.0,
                        "blocked": False,
                        "blockers": [],
                        "snapshot_data": {
                            "id": "mis_drone_jam",
                            "stage": "Research",
                            "progress": 30.0,
                            "blocked": False,
                            "blockers": [],
                            "resources": ["Ollama model"],
                            "confidence_score": 0.85,
                            "next_action": "Search for RF datasheets.",
                            "completed_stages": [],
                            "pending_stages": ["Research", "Design", "Simulation", "Testing", "Documentation"]
                        }
                    }
                ]
                cls.save_checkpoints(initial)
                return initial
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []

    @classmethod
    def save_checkpoints(cls, data: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _checkpoint_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def create_checkpoint(cls, mission_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with cls._lock:
            checkpoints = cls.load_checkpoints()
            chp_id = f"chp_{int(time.time())}_{len(checkpoints)}"
            checkpoint = {
                "checkpoint_id": chp_id,
                "mission_id": mission_id,
                "timestamp": time.time(),
                "stage": state.get("stage", ""),
                "progress": state.get("progress", 0.0),
                "blocked": state.get("blocked", False),
                "blockers": list(state.get("blockers", [])),
                "snapshot_data": dict(state)
            }
            checkpoints.append(checkpoint)
            cls.save_checkpoints(checkpoints)
            return checkpoint

    @classmethod
    def get_checkpoints_for_mission(cls, mission_id: str) -> list[dict[str, Any]]:
        with cls._lock:
            return [c for c in cls.load_checkpoints() if c["mission_id"] == mission_id]

    @classmethod
    def rollback_to_checkpoint(cls, mission_id: str, checkpoint_id: str) -> dict[str, Any] | None:
        with cls._lock:
            checkpoints = cls.load_checkpoints()
            for chp in checkpoints:
                if chp["checkpoint_id"] == checkpoint_id and chp["mission_id"] == mission_id:
                    state = dict(chp["snapshot_data"])
                    MissionState.set_state(mission_id, state)
                    return state
            return None
