from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _knowledge_file_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "cross_mission_knowledge.json"


class CrossMissionLearning:
    _lock = threading.RLock()

    @classmethod
    def load_knowledge(cls) -> list[dict[str, Any]]:
        with cls._lock:
            path = _knowledge_file_path()
            if not path.exists():
                # Seed a default bug knowledge
                initial = [
                    {
                        "knowledge_id": "knw_001",
                        "source_mission_id": "mis_drone_jam",
                        "topic": "STM32 SPI Clock Speed Bug",
                        "details": "Setting clock prescaler below SPI_BAUDRATEPRESCALER_16 triggers frame transmission latency errors on STM32F4 boards.",
                        "timestamp": time.time() - 86400
                    }
                ]
                cls.save_knowledge(initial)
                return initial
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []

    @classmethod
    def save_knowledge(cls, data: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _knowledge_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def publish_finding(cls, mission_id: str, topic: str, details: str) -> dict[str, Any]:
        with cls._lock:
            knowledge = cls.load_knowledge()
            knw_id = f"knw_{int(time.time())}_{len(knowledge)}"
            entry = {
                "knowledge_id": knw_id,
                "source_mission_id": mission_id,
                "topic": topic,
                "details": details,
                "timestamp": time.time()
            }
            knowledge.append(entry)
            cls.save_knowledge(knowledge)
            return entry

    @classmethod
    def scan_for_warnings(cls, context_text: str) -> list[dict[str, Any]]:
        """Scans if any published topic keywords match the input text."""
        with cls._lock:
            knowledge = cls.load_knowledge()
            warnings = []
            text_lower = context_text.lower()
            for k in knowledge:
                topic = k["topic"].lower()
                # Split topic into keywords
                words = [w for w in topic.split() if len(w) > 2]
                # If any key term matches, return warning
                if any(w in text_lower for w in words):
                    warnings.append(k)
            return warnings
