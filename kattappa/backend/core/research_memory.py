"""
Step 10.0 — Research Memory.
Tracks processing history of documents, summaries, and proposals to prevent spam/duplicates.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _memory_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "research_memory.json"


class ResearchMemory:
    _lock = threading.RLock()

    @classmethod
    def load_memory(cls) -> dict[str, list[str]]:
        with cls._lock:
            path = _memory_path()
            if not path.exists():
                return {
                    "already_read": [],
                    "already_summarized": [],
                    "already_proposed": [],
                    "already_rejected": []
                }
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
                for key in ("already_read", "already_summarized", "already_proposed", "already_rejected"):
                    if key not in data or not isinstance(data[key], list):
                        data[key] = []
                return data
            except Exception:
                return {
                    "already_read": [],
                    "already_summarized": [],
                    "already_proposed": [],
                    "already_rejected": []
                }

    @classmethod
    def save_memory(cls, memory: dict[str, list[str]]) -> None:
        with cls._lock:
            path = _memory_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(memory, indent=2), encoding="utf-8")

    @classmethod
    def is_duplicate_document(cls, title: str) -> bool:
        with cls._lock:
            mem = cls.load_memory()
            return title.strip().lower() in {t.lower() for t in mem["already_read"]}

    @classmethod
    def is_duplicate_summary(cls, doc_id: str) -> bool:
        with cls._lock:
            mem = cls.load_memory()
            return doc_id in mem["already_summarized"]

    @classmethod
    def is_duplicate_proposal(cls, title: str) -> bool:
        with cls._lock:
            mem = cls.load_memory()
            return title.strip().lower() in {t.lower() for t in mem["already_proposed"]}

    @classmethod
    def is_duplicate_rejection(cls, title: str) -> bool:
        with cls._lock:
            mem = cls.load_memory()
            return title.strip().lower() in {t.lower() for t in mem["already_rejected"]}

    @classmethod
    def record_read(cls, title: str) -> None:
        with cls._lock:
            mem = cls.load_memory()
            t_clean = title.strip()
            if t_clean.lower() not in {t.lower() for t in mem["already_read"]}:
                mem["already_read"].append(t_clean)
                cls.save_memory(mem)

    @classmethod
    def record_summarized(cls, doc_id: str) -> None:
        with cls._lock:
            mem = cls.load_memory()
            if doc_id not in mem["already_summarized"]:
                mem["already_summarized"].append(doc_id)
                cls.save_memory(mem)

    @classmethod
    def record_proposed(cls, title: str) -> None:
        with cls._lock:
            mem = cls.load_memory()
            t_clean = title.strip()
            if t_clean.lower() not in {t.lower() for t in mem["already_proposed"]}:
                mem["already_proposed"].append(t_clean)
                cls.save_memory(mem)

    @classmethod
    def record_rejected(cls, title: str) -> None:
        with cls._lock:
            mem = cls.load_memory()
            t_clean = title.strip()
            if t_clean.lower() not in {t.lower() for t in mem["already_rejected"]}:
                mem["already_rejected"].append(t_clean)
                cls.save_memory(mem)
