"""Reflection Engine (Layer 8 component).

Analyzes logs and execution traces, performs significance checks, and proposes reflections.
Also contains Phase 4 JSON-based reflection manager for backward compatibility and API endpoints.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from backend.core.model_router import ask_model
from backend.core.logger import log_event
from backend.core.reflection_memory import ReflectionMemory
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
    """Reflection Engine (Layer 8 component).

    Responsible for analyzing logs and execution traces, performing significance checks,
    and invoking the model to safely generate improvement proposals under governance guidelines.
    Also handles Phase 4 JSON-backed persistent observations.
    """

    # --- Layer 8 Significance Evaluation and Proposals ---

    @classmethod
    def evaluate_significance(cls, logs_text: str) -> dict[str, Any]:
        """Performs a deterministic significance evaluation on raw log traces.
        
        Analyzes tool exit codes, exception counts, and explicit error matches.
        """
        # Parse common failure indicators:
        # Non-zero exit codes: e.g. "exit_code=1" or similar
        exit_code_failures = len(re.findall(r"exit_code=[1-9]", logs_text))
        
        # Exception patterns
        exceptions = len(re.findall(r"(?i)\b(exception|failed|error|runtimeerror|valueerror|connectionerror)\b", logs_text))
        
        # Thumbs down / user rejection indicators
        thumbs_down = len(re.findall(r"(?i)\b(thumbs down|user rejected|thumbs-down|bad response)\b", logs_text))
        
        total_runs = len(re.findall(r"(?i)\b(run_task|session_start|execute_command)\b", logs_text)) or 1
        
        error_rate = (exit_code_failures + exceptions + thumbs_down) / total_runs
        
        return {
            "exit_code_failures": exit_code_failures,
            "exceptions": exceptions,
            "thumbs_down": thumbs_down,
            "total_runs": total_runs,
            "error_rate": error_rate,
            "actionable": (exit_code_failures > 0 or exceptions > 3 or thumbs_down > 0 or error_rate > 0.05)
        }

    @classmethod
    def analyze_and_propose(cls, logs_text: str, source_window_days: int = 7) -> str | None:
        """Parses interaction logs, runs significance checks, and proposes a reflection candidate.
        
        Returns the created reflection ID, or None if no actionable issue was found.
        """
        sig = cls.evaluate_significance(logs_text)
        
        # If no significant issues exist, do not generate proposals (avoids manufactured problems)
        if not sig["actionable"]:
            log_event("reflection_engine: no significant actionable issue detected in logs.")
            return None
            
        # Invoke model with a clean prompt requesting a structured JSON response
        prompt = (
            f"Analyze the following execution logs and identify the root cause of failures.\n"
            f"--- LOGS ---\n{logs_text[:4000]}\n------------\n\n"
            f"Requirements:\n"
            f"1. Never propose self-modification of source code files.\n"
            f"2. Propose only behavior, retrieval, prompt, or tool parameter improvements.\n"
            f"3. Respond strictly with a JSON object containing these keys:\n"
            f"   - 'category': one of 'RETRIEVAL', 'REASONING', 'TOOLING', 'ALIGNMENT', 'SAFETY', 'PERFORMANCE', 'SUCCESS'\n"
            f"   - 'problem': clear explanation of the failure\n"
            f"   - 'cause': underlying root cause\n"
            f"   - 'improvement': proposed prompt or parameter change proposal (without modifying python files)\n"
            f"   - 'confidence': confidence score between 0.0 and 1.0\n"
            f"4. If nothing is actionable, return the category 'SUCCESS' and empty strings for other fields."
        )
        
        try:
            response = ask_model(prompt, role="coder")
            
            # Simple JSON extraction in case model returned extra markdown backticks
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                log_event("reflection_engine: failed to parse JSON from LLM response. Using deterministic fallback.")
                return cls._create_fallback_reflection(sig, source_window_days)
                
            data = json.loads(json_match.group(0))
            category = data.get("category", "PERFORMANCE").strip().upper()
            problem = data.get("problem", "Log errors detected").strip()
            cause = data.get("cause", "Exceptions / non-zero exits in logs").strip()
            improvement = data.get("improvement", "Improve search parameters or retry limits").strip()
            confidence = float(data.get("confidence", 0.7))
            
            if category == "SUCCESS" or not problem or problem.lower() == "none":
                return None
                
            # Submit to Reflection Memory (which handles deduplication)
            ref_id = ReflectionMemory.propose_reflection(
                category=category,
                problem=problem,
                cause=cause,
                improvement=improvement,
                confidence=confidence,
                source_window_days=source_window_days
            )
            return ref_id
            
        except Exception as exc:
            log_event(f"reflection_engine: LLM analysis failed: {exc}. Falling back to deterministic proposal.")
            return cls._create_fallback_reflection(sig, source_window_days)

    @classmethod
    def _create_fallback_reflection(cls, sig_data: dict, source_window_days: int) -> str:
        """Deterministic partial-capture fallback when LLM schema generation fails."""
        problem = f"Observed {sig_data['exceptions']} exceptions and {sig_data['exit_code_failures']} exit failures."
        cause = "System exit code mismatches or unhandled exceptions."
        improvement = "Increase retry delays or verify prerequisite environment settings."
        
        return ReflectionMemory.propose_reflection(
            category="PERFORMANCE",
            problem=problem,
            cause=cause,
            improvement=improvement,
            confidence=0.6,
            source_window_days=source_window_days
        )

    # --- Phase 4 JSON-Backed Observation Persistence and Management ---

    _lock = threading.RLock()

    MIN_EVIDENCE_COUNT = 3
    MIN_EVIDENCE_SOURCES = 2
    DEFAULT_WINDOW_DAYS = 30
    DEDUP_SIMILARITY = 0.6

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
