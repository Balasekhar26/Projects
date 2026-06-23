from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from backend.core.config import runtime_data_root


def _memory_file_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "long_term_memory.json"


class LongTermMemory:
    @classmethod
    def load_memory(cls) -> dict[str, Any]:
        path = _memory_file_path()
        if not path.exists():
            return {
                "ResearchMemory": [],
                "ProjectMemory": [],
                "UserMemory": {"clearance_level": "operator", "name": "Bala"},
                "ToolMemory": [],
                "FailureMemory": []
            }
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "ResearchMemory": [],
                "ProjectMemory": [],
                "UserMemory": {"clearance_level": "operator", "name": "Bala"},
                "ToolMemory": [],
                "FailureMemory": []
            }

    @classmethod
    def save_memory(cls, memory: dict[str, Any]) -> None:
        path = _memory_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(memory, indent=2), encoding="utf-8")

    @classmethod
    def add_record(cls, partition: str, record: Any) -> None:
        memory = cls.load_memory()
        if partition not in memory:
            memory[partition] = []
        if isinstance(memory[partition], list):
            memory[partition].append(record)
        else:
            memory[partition] = record
        cls.save_memory(memory)

    @classmethod
    def get_partition(cls, partition: str) -> Any:
        return cls.load_memory().get(partition, [])
