"""Reflection Engine (Phase 4).

Learns from successes and failures by turning outcomes into reflection records.
It embodies the safety rules established in the earlier reviews:

* **Hypotheses, not mutations** - reflection NEVER edits memory, weights, or
  prompts. It proposes; governance (a human) accepts. There is no apply/execute
  method here.
* **Corroboration** - a reflection is only *actionable* after >= 3 supporting
  observations from >= 2 independent evidence sources, so a single instance (or
  one model talking to itself) cannot mint a durable lesson.
* **Dedup, not regenerate** - a similar problem increments the existing pending
  record's evidence instead of spawning duplicates (no regeneration treadmill).
* **Expiration** - unaccepted reflections expire after a window (default 30d).

Deterministic and persistent (JSON under the runtime data dir).
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _path() -> Path:
    return runtime_data_root() / "backend" / "data" / "reflections.json"


_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(text.lower()) if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class ReflectionCategory(str, Enum):
    RETRIEVAL = "retrieval"
    REASONING = "reasoning"
    TOOLING = "tooling"
    ALIGNMENT = "alignment"
    SAFETY = "safety"
    PERFORMANCE = "performance"
    SUCCESS = "success"

    @classmethod
    def coerce(cls, value: "ReflectionCategory | str") -> "ReflectionCategory":
        return value if isinstance(value, cls) else cls(str(value).strip().lower())


class ReflectionStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ReflectionEngine:
    _lock = threading.RLock()

    MIN_EVIDENCE_COUNT = 3
    MIN_EVIDENCE_SOURCES = 2
    DEFAULT_WINDOW_DAYS = 30
    DEDUP_SIMILARITY = 0.6

    # -- persistence -------------------------------------------------------
    @classmethod
    def _load(cls) -> dict[str, Any]:
        try:
            p = _path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"reflections": []}

    @classmethod
    def _save(cls, data: dict[str, Any]) -> None:
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    # -- proposing ---------------------------------------------------------
    @classmethod
    def reflect(
        cls,
        problem: str,
        cause: str,
        improvement: str,
        *,
        category: ReflectionCategory | str = ReflectionCategory.REASONING,
        evidence_source: str = "reasoning",
        confidence: int = 50,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> dict[str, Any]:
        """Record an observation. Dedups into an existing pending reflection."""
        problem = problem.strip()
        if not problem:
            raise ValueError("Reflection problem cannot be empty")
        category = ReflectionCategory.coerce(category)
        confidence = max(0, min(100, int(confidence)))
        ptokens = _tokens(problem)

        with cls._lock:
            data = cls._load()
            reflections = data.setdefault("reflections", [])

            # Dedup: fold into a similar PENDING reflection.
            for rec in reflections:
                if rec["status"] != ReflectionStatus.PENDING.value:
                    continue
                if _jaccard(ptokens, _tokens(rec["problem"])) >= cls.DEDUP_SIMILARITY:
                    sources = set(rec.get("evidence_sources", []))
                    sources.add(evidence_source)
                    rec["evidence_sources"] = sorted(sources)
                    rec["evidence_count"] = int(rec.get("evidence_count", 1)) + 1
                    rec["confidence"] = max(int(rec.get("confidence", 0)), confidence)
                    rec["updated_at"] = time.time()
                    cls._save(data)
                    return rec

            now = time.time()
            rec = {
                "id": uuid.uuid4().hex[:12],
                "category": category.value,
                "problem": problem,
                "cause": cause.strip(),
                "improvement": improvement.strip(),
                "confidence": confidence,
                "evidence_count": 1,
                "evidence_sources": [evidence_source],
                "status": ReflectionStatus.PENDING.value,
                "window_days": window_days,
                "created_at": now,
                "updated_at": now,
                "expires_at": now + window_days * 86400,
            }
            reflections.append(rec)
            cls._save(data)
            return rec

    # -- eligibility & governance -----------------------------------------
    @classmethod
    def is_actionable(cls, rec: dict[str, Any]) -> bool:
        return (
            int(rec.get("evidence_count", 0)) >= cls.MIN_EVIDENCE_COUNT
            and len(rec.get("evidence_sources", [])) >= cls.MIN_EVIDENCE_SOURCES
        )

    @classmethod
    def accept(cls, reflection_id: str) -> dict[str, Any]:
        """Governance acceptance. Returns the improvement to apply EXTERNALLY.

        Acceptance does NOT mutate any memory/weights/prompts itself.
        """
        with cls._lock:
            data = cls._load()
            rec = cls._find(data, reflection_id)
            if rec is None:
                raise KeyError(f"No reflection {reflection_id!r}")
            if not cls.is_actionable(rec):
                raise ValueError(
                    f"Reflection not actionable: needs >= {cls.MIN_EVIDENCE_COUNT} observations "
                    f"from >= {cls.MIN_EVIDENCE_SOURCES} sources"
                )
            rec["status"] = ReflectionStatus.ACCEPTED.value
            rec["updated_at"] = time.time()
            cls._save(data)
            return rec

    @classmethod
    def reject(cls, reflection_id: str) -> dict[str, Any]:
        with cls._lock:
            data = cls._load()
            rec = cls._find(data, reflection_id)
            if rec is None:
                raise KeyError(f"No reflection {reflection_id!r}")
            rec["status"] = ReflectionStatus.REJECTED.value
            rec["updated_at"] = time.time()
            cls._save(data)
            return rec

    @classmethod
    def expire_old(cls, *, now: float | None = None) -> int:
        now = now or time.time()
        expired = 0
        with cls._lock:
            data = cls._load()
            for rec in data.get("reflections", []):
                if rec["status"] == ReflectionStatus.PENDING.value and now >= rec.get("expires_at", 0):
                    rec["status"] = ReflectionStatus.EXPIRED.value
                    rec["updated_at"] = now
                    expired += 1
            cls._save(data)
        return expired

    # -- queries -----------------------------------------------------------
    @staticmethod
    def _find(data: dict[str, Any], reflection_id: str) -> dict[str, Any] | None:
        return next((r for r in data.get("reflections", []) if r["id"] == reflection_id), None)

    @classmethod
    def get(cls, reflection_id: str) -> dict[str, Any] | None:
        return cls._find(cls._load(), reflection_id)

    @classmethod
    def list_reflections(cls, status: str | None = None) -> list[dict[str, Any]]:
        items = list(cls._load().get("reflections", []))
        if status:
            items = [r for r in items if r["status"] == status]
        return items

    @classmethod
    def actionable(cls) -> list[dict[str, Any]]:
        return [r for r in cls.list_reflections(ReflectionStatus.PENDING.value)
                if cls.is_actionable(r)]

    @classmethod
    def status(cls) -> dict[str, Any]:
        items = cls.list_reflections()
        by_status: dict[str, int] = {s.value: 0 for s in ReflectionStatus}
        by_category: dict[str, int] = {c.value: 0 for c in ReflectionCategory}
        for r in items:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            by_category[r["category"]] = by_category.get(r["category"], 0) + 1
        return {
            "total": len(items),
            "by_status": by_status,
            "by_category": by_category,
            "actionable": len(cls.actionable()),
        }

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._save({"reflections": []})
