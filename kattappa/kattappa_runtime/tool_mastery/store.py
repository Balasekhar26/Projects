"""
Tool Mastery Store — ToolProfile + ToolMastery registry
=========================================================

ToolCategory
    Classification of tool type for reporting and routing.

ToolProfile
    Per-tool mastery data with computed mastery_score.

ToolMastery
    Registry of all ToolProfiles, JSON-persisted, thread-safe.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "tool_profiles.json")

# EMA smoothing for latency
_LATENCY_ALPHA   = 0.2
_DEFAULT_LATENCY = 500.0   # ms, assumed if no data

# Latency penalty: above this ms threshold, latency_penalty starts rising
_LATENCY_BASELINE = 200.0   # ms
_LATENCY_MAX      = 5000.0  # ms (full penalty at this level)

# Confidence deltas per outcome
_DELTA_SUCCESS = +0.05
_DELTA_FAILURE = -0.08


class ToolCategory(str, Enum):
    SHELL       = "shell"        # git, python, bash, etc.
    SEARCH      = "search"       # web_search, wikipedia, arxiv
    CODE        = "code"         # code_runner, linter, formatter
    MCP         = "mcp"          # MCP server tools
    API         = "api"          # external REST APIs
    INTERNAL    = "internal"     # Kattappa's own engines
    DATABASE    = "database"     # vector_db, SQL, etc.
    OTHER       = "other"


@dataclass
class ToolProfile:
    """Per-tool mastery profile."""
    name:            str          = "unknown"
    category:        ToolCategory = ToolCategory.OTHER
    confidence:      float        = 0.6
    attempts:        int          = 0
    successes:       int          = 0
    avg_latency_ms:  float        = _DEFAULT_LATENCY
    last_used:       str          = ""
    common_failures: List[str]    = field(default_factory=list)
    notes:           str          = ""

    @property
    def success_rate(self) -> float:
        if self.attempts == 0:
            return -1.0
        return self.successes / self.attempts

    @property
    def latency_penalty(self) -> float:
        """Normalised latency penalty in [0.0, 1.0]. 0 = fast, 1 = very slow."""
        excess = max(0.0, self.avg_latency_ms - _LATENCY_BASELINE)
        return min(1.0, excess / (_LATENCY_MAX - _LATENCY_BASELINE))

    @property
    def mastery_score(self) -> float:
        """
        Composite mastery score in [0.0, 1.0].
        Combines confidence, success rate, and latency efficiency.
        """
        sr = max(0.0, self.success_rate)  # treat -1.0 as 0.0 if no data
        score = (
            0.50 * self.confidence
            + 0.30 * sr
            + 0.20 * (1.0 - self.latency_penalty)
        )
        return round(min(1.0, score), 4)

    @property
    def mastery_label(self) -> str:
        s = self.mastery_score
        if s >= 0.85: return "Expert"
        if s >= 0.70: return "Proficient"
        if s >= 0.50: return "Developing"
        if s >= 0.30: return "Beginner"
        return "Critical Gap"

    def to_dict(self) -> dict:
        return {
            "name":            self.name,
            "category":        self.category.value,
            "confidence":      round(self.confidence, 4),
            "attempts":        self.attempts,
            "successes":       self.successes,
            "success_rate":    round(self.success_rate, 4),
            "avg_latency_ms":  round(self.avg_latency_ms, 1),
            "latency_penalty": round(self.latency_penalty, 4),
            "mastery_score":   self.mastery_score,
            "mastery_label":   self.mastery_label,
            "last_used":       self.last_used,
            "common_failures": self.common_failures,
            "notes":           self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ToolProfile":
        d = dict(d)
        d["category"] = ToolCategory(d.get("category", "other"))
        # Remove computed properties before passing to __init__
        for k in ("success_rate", "latency_penalty", "mastery_score", "mastery_label"):
            d.pop(k, None)
        return cls(**d)


class ToolMastery:
    """
    Registry of all ToolProfiles with JSON persistence.

    Thread-safe. All writes flush immediately.

    Usage
    -----
        tm = ToolMastery()

        # Record a tool use
        tm.record_use("git", succeeded=True, latency_ms=35.0)
        tm.record_use("web_search", succeeded=False, latency_ms=4500.0,
                      failure_note="connection timeout")

        # Query
        profile = tm.get("git")
        print(tm.summary_table())
        print(tm.weakest_tools(n=3))
    """

    def __init__(self, path: str = _DEFAULT_PATH):
        self._path: str = path
        self._lock: Lock = Lock()
        self._profiles: Dict[str, ToolProfile] = self._load()

    # ------------------------------------------------------------------
    # Public — write
    # ------------------------------------------------------------------

    def record_use(
        self,
        tool_name:     str,
        succeeded:     bool,
        latency_ms:    float               = _DEFAULT_LATENCY,
        category:      ToolCategory        = ToolCategory.OTHER,
        failure_note:  Optional[str]       = None,
    ) -> ToolProfile:
        """
        Record one tool invocation.

        Parameters
        ----------
        tool_name : str
            Unique name of the tool (e.g. "git", "web_search", "arxiv").
        succeeded : bool
            Whether the tool call achieved its goal.
        latency_ms : float
            Wall-clock time of the tool call in milliseconds.
        category : ToolCategory
            Type classification (set on first use; ignored after).
        failure_note : str | None
            Short description of what went wrong (for common_failures log).

        Returns
        -------
        ToolProfile
            Updated profile for this tool.
        """
        with self._lock:
            profile = self._get_or_create(tool_name, category)

            profile.attempts += 1
            if succeeded:
                profile.successes += 1

            # Update confidence (clamped)
            delta = _DELTA_SUCCESS if succeeded else _DELTA_FAILURE
            profile.confidence = max(0.0, min(1.0, profile.confidence + delta))

            # EMA latency
            profile.avg_latency_ms = (
                _LATENCY_ALPHA * latency_ms
                + (1 - _LATENCY_ALPHA) * profile.avg_latency_ms
            )

            # Timestamp
            profile.last_used = datetime.now(timezone.utc).isoformat()

            # Failure note
            if failure_note and not succeeded:
                note_lower = failure_note.lower().strip()
                existing   = [n.lower() for n in profile.common_failures]
                if note_lower not in existing:
                    profile.common_failures.append(failure_note.strip())
                    profile.common_failures = profile.common_failures[-10:]  # keep last 10

            self._save()
            return profile

    def register_tool(
        self,
        tool_name: str,
        category:  ToolCategory = ToolCategory.OTHER,
        notes:     str          = "",
    ) -> ToolProfile:
        """Register a tool without recording a use (e.g. at startup)."""
        with self._lock:
            profile = self._get_or_create(tool_name, category)
            if notes:
                profile.notes = notes
            self._save()
            return profile

    # ------------------------------------------------------------------
    # Public — read
    # ------------------------------------------------------------------

    def get(self, tool_name: str) -> Optional[ToolProfile]:
        with self._lock:
            return self._profiles.get(tool_name)

    def get_or_default(self, tool_name: str, category: ToolCategory = ToolCategory.OTHER) -> ToolProfile:
        with self._lock:
            return self._get_or_create(tool_name, category)

    def all_profiles(self) -> List[ToolProfile]:
        with self._lock:
            return sorted(self._profiles.values(), key=lambda p: p.mastery_score, reverse=True)

    def weakest_tools(self, n: int = 5) -> List[ToolProfile]:
        with self._lock:
            return sorted(self._profiles.values(), key=lambda p: p.mastery_score)[:n]

    def strongest_tools(self, n: int = 5) -> List[ToolProfile]:
        return self.all_profiles()[:n]

    def by_category(self, category: ToolCategory) -> List[ToolProfile]:
        with self._lock:
            return [p for p in self._profiles.values() if p.category == category]

    def count(self) -> int:
        with self._lock:
            return len(self._profiles)

    def summary_table(self) -> str:
        """
        ASCII summary table of all tools.

        Tool                 | Cat      | Mastery | Score | Tries | Win%  | Latency
        git                  | shell    | Expert  |  0.88 |    31 | 94.0% |   35ms
        web_search           | search   | Devel.. |  0.52 |    10 | 60.0% | 1200ms
        """
        profiles = self.all_profiles()
        if not profiles:
            return "No tool profiles tracked yet."

        hdr = (
            f"{'Tool':<22} | {'Cat':<8} | {'Mastery':<12} | "
            f"{'Score':>5} | {'Tries':>5} | {'Win%':>6} | {'Latency':>8}"
        )
        sep  = "-" * len(hdr)
        rows = [hdr, sep]

        for p in profiles:
            sr  = f"{p.success_rate*100:5.1f}%" if p.success_rate >= 0 else "  N/A "
            lat = f"{p.avg_latency_ms:>5.0f}ms"
            rows.append(
                f"{p.name:<22} | {p.category.value:<8} | {p.mastery_label:<12} | "
                f"{p.mastery_score:>5.2f} | {p.attempts:>5} | {sr:>6} | {lat:>8}"
            )
        return "\n".join(rows)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _get_or_create(self, name: str, category: ToolCategory) -> ToolProfile:
        """Must be called under self._lock."""
        if name not in self._profiles:
            self._profiles[name] = ToolProfile(name=name, category=category)
        return self._profiles[name]

    def _load(self) -> Dict[str, ToolProfile]:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                k: ToolProfile.from_dict(v)
                for k, v in data.items()
                if isinstance(v, dict)
            }
        except (json.JSONDecodeError, TypeError):
            return {}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(
                    {k: v.to_dict() for k, v in self._profiles.items()},
                    f, indent=2, ensure_ascii=False,
                )
        except OSError:
            pass
