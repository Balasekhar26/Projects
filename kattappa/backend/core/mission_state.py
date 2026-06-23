from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _state_file_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "mission_states.json"


class MissionState:
    _lock = threading.RLock()

    @classmethod
    def load_states(cls) -> dict[str, dict[str, Any]]:
        with cls._lock:
            path = _state_file_path()
            if not path.exists():
                # Initial seed mission states
                initial = {
                    "mis_drone_jam": {
                        "id": "mis_drone_jam",
                        "stage": "Design",
                        "progress": 63.0,
                        "blocked": False,
                        "blockers": [],
                        "resources": ["Ollama model", "RF scanner library"],
                        "confidence_score": 0.88,
                        "next_action": "Generate BOM for target board configuration.",
                        "completed_stages": ["Research"],
                        "pending_stages": ["Design", "Simulation", "Testing", "Documentation"],
                        "updated_at": time.time()
                    }
                }
                cls.save_states(initial)
                return initial
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}

    @classmethod
    def save_states(cls, data: dict[str, dict[str, Any]]) -> None:
        with cls._lock:
            path = _state_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def get_state(cls, mission_id: str) -> dict[str, Any] | None:
        with cls._lock:
            return cls.load_states().get(mission_id)

    @classmethod
    def set_state(cls, mission_id: str, state: dict[str, Any]) -> None:
        with cls._lock:
            states = cls.load_states()
            state["updated_at"] = time.time()
            states[mission_id] = state
            cls.save_states(states)

    @classmethod
    def update_progress(cls, mission_id: str, progress: float, stage: str | None = None) -> None:
        with cls._lock:
            states = cls.load_states()
            if mission_id in states:
                states[mission_id]["progress"] = max(0.0, min(100.0, progress))
                if stage:
                    states[mission_id]["stage"] = stage
                    # Update completed/pending stages list
                    if stage in states[mission_id]["pending_stages"]:
                        idx = states[mission_id]["pending_stages"].index(stage)
                        completed = states[mission_id].setdefault("completed_stages", [])
                        for s in states[mission_id]["pending_stages"][:idx]:
                            if s not in completed:
                                completed.append(s)
                        states[mission_id]["pending_stages"] = states[mission_id]["pending_stages"][idx:]
                states[mission_id]["updated_at"] = time.time()
                cls.save_states(states)

    @classmethod
    def set_blocked(cls, mission_id: str, blocked: bool, blocker: str | None = None) -> None:
        with cls._lock:
            states = cls.load_states()
            if mission_id in states:
                states[mission_id]["blocked"] = blocked
                blockers = states[mission_id].setdefault("blockers", [])
                if blocked and blocker:
                    if blocker not in blockers:
                        blockers.append(blocker)
                elif not blocked:
                    states[mission_id]["blockers"] = []
                states[mission_id]["updated_at"] = time.time()
                cls.save_states(states)
