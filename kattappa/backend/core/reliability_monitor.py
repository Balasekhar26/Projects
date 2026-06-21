"""Reliability Monitor (Phase 4).

Tracks how often each agent/validator is actually right over time, so the Router
and Consensus can use measured performance instead of static assumptions.

Deterministic and persistent (JSON under the runtime data dir). It records
outcomes; it never decides or executes anything.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _path() -> Path:
    return runtime_data_root() / "backend" / "data" / "reliability.json"


class ReliabilityMonitor:
    """Per-agent success tracking with cumulative and recent-window accuracy."""

    _lock = threading.Lock()
    _recent_window = 50
    _default_accuracy = 0.5

    # -- persistence -------------------------------------------------------
    @classmethod
    def _load(cls) -> dict[str, Any]:
        try:
            p = _path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"agents": {}}

    @classmethod
    def _save(cls, data: dict[str, Any]) -> None:
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    # -- recording ---------------------------------------------------------
    @classmethod
    def record_outcome(cls, agent: str, success: bool) -> dict[str, Any]:
        with cls._lock:
            data = cls._load()
            agents = data.setdefault("agents", {})
            rec = agents.setdefault(agent, {"total": 0, "success": 0, "recent": []})
            rec["total"] += 1
            rec["success"] += 1 if success else 0
            recent = rec.setdefault("recent", [])
            recent.append(1 if success else 0)
            if len(recent) > cls._recent_window:
                rec["recent"] = recent[-cls._recent_window:]
            cls._save(data)
            return cls._stats_for(agent, rec)

    # -- queries -----------------------------------------------------------
    @staticmethod
    def _stats_for(agent: str, rec: dict[str, Any]) -> dict[str, Any]:
        total = int(rec.get("total", 0))
        success = int(rec.get("success", 0))
        recent = rec.get("recent", [])
        accuracy = success / total if total else None
        recent_accuracy = sum(recent) / len(recent) if recent else None
        return {
            "agent": agent,
            "total": total,
            "success": success,
            "accuracy": round(accuracy, 4) if accuracy is not None else None,
            "recent_accuracy": round(recent_accuracy, 4) if recent_accuracy is not None else None,
        }

    @classmethod
    def accuracy(cls, agent: str) -> float | None:
        with cls._lock:
            rec = cls._load().get("agents", {}).get(agent)
        if not rec or not rec.get("total"):
            return None
        return rec["success"] / rec["total"]

    @classmethod
    def weight_hint(cls, agent: str) -> float:
        """A reliability factor in [0,1]; defaults to neutral when unseen."""
        acc = cls.accuracy(agent)
        return acc if acc is not None else cls._default_accuracy

    @classmethod
    def stats(cls) -> dict[str, Any]:
        with cls._lock:
            data = cls._load()
        return {
            "agents": [cls._stats_for(name, rec)
                       for name, rec in sorted(data.get("agents", {}).items())],
        }

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._save({"agents": {}})
