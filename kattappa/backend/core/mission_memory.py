from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _mission_file_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "mission_memory.json"


class MissionMemory:
    _lock = threading.RLock()

    @classmethod
    def load_missions(cls) -> dict[str, dict[str, Any]]:
        with cls._lock:
            path = _mission_file_path()
            if not path.exists():
                # Initial seed missions
                initial = {
                    "mis_drone_jam": {
                        "id": "mis_drone_jam",
                        "title": "Drone Jammer Design",
                        "description": "Develop a multi-frequency RF drone jamming prototype.",
                        "stages": ["Research", "Design", "Simulation", "Testing", "Documentation"],
                        "current_stage": "Design",
                        "status": "running",
                        "created_at": time.time() - 86400 * 3,
                        "completed_at": None,
                        "lessons_learned": ["RF simulation tools require GPU calibration."],
                        "user_project": "Drone Jammer Project"
                    },
                    "mis_stm32_boot": {
                        "id": "mis_stm32_boot",
                        "title": "STM32 Bootloader",
                        "description": "Secure custom bootloader for STM32 microcontrollers.",
                        "stages": ["Requirements", "Implementation", "Testing", "Deployment"],
                        "current_stage": "Deployment",
                        "status": "completed",
                        "created_at": time.time() - 86400 * 7,
                        "completed_at": time.time() - 86400 * 4,
                        "lessons_learned": ["Enforce dual-bank verification during boot cycles."],
                        "user_project": "STM32 Secure Boot"
                    }
                }
                cls.save_missions(initial)
                return initial
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}

    @classmethod
    def save_missions(cls, data: dict[str, dict[str, Any]]) -> None:
        with cls._lock:
            path = _mission_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def add_mission(cls, mission: dict[str, Any]) -> None:
        with cls._lock:
            missions = cls.load_missions()
            missions[mission["id"]] = mission
            cls.save_missions(missions)

    @classmethod
    def get_mission(cls, mission_id: str) -> dict[str, Any] | None:
        with cls._lock:
            return cls.load_missions().get(mission_id)

    @classmethod
    def update_mission_status(cls, mission_id: str, status: str, current_stage: str | None = None) -> None:
        with cls._lock:
            missions = cls.load_missions()
            if mission_id in missions:
                missions[mission_id]["status"] = status
                if current_stage:
                    missions[mission_id]["current_stage"] = current_stage
                if status in {"completed", "failed"}:
                    missions[mission_id]["completed_at"] = time.time()
                missions[mission_id]["updated_at"] = time.time()
                cls.save_missions(missions)

    @classmethod
    def add_lesson(cls, mission_id: str, lesson: str) -> None:
        with cls._lock:
            missions = cls.load_missions()
            if mission_id in missions:
                lessons = missions[mission_id].setdefault("lessons_learned", [])
                if lesson not in lessons:
                    lessons.append(lesson)
                cls.save_missions(missions)
