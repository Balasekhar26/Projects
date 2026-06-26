"""
Skill Memory Store — SkillProfile + SkillMemory
================================================

SkillProfile
    A single domain's complete self-model.

SkillMemory
    The registry of all SkillProfiles, persisted to JSON.
    Thread-safe. All writes immediately flush to disk.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "skill_profiles.json")
_DEFAULT_CONFIDENCE = 0.6

# EMA smoothing factor for learning velocity
_VELOCITY_ALPHA = 0.2


@dataclass
class SkillProfile:
    """
    Self-model of one skill/knowledge domain.

    Fields
    ------
    domain : str
        Identifier for the skill (e.g. "translation", "python", "rf_systems").
    confidence : float
        Current aggregate confidence level [0.0 – 1.0].
    attempts : int
        Total number of times this skill was exercised.
    successes : int
        Number of successful attempts.
    learning_velocity : float
        EMA of confidence gain per 10 attempts. Positive = improving.
    last_used : str
        ISO-8601 UTC timestamp of last attempt.
    weaknesses : List[str]
        Identified knowledge gaps from the Learning Engine.
    notes : str
        Free-form annotations.
    """
    domain:             str         = "general"
    confidence:         float       = _DEFAULT_CONFIDENCE
    attempts:           int         = 0
    successes:          int         = 0
    learning_velocity:  float       = 0.0
    last_used:          str         = ""
    weaknesses:         List[str]   = field(default_factory=list)
    notes:              str         = ""

    @property
    def success_rate(self) -> float:
        """Live-computed success rate. Returns -1.0 if no attempts yet."""
        if self.attempts == 0:
            return -1.0
        return self.successes / self.attempts

    @property
    def confidence_label(self) -> str:
        """Human-readable confidence band."""
        c = self.confidence
        if c >= 0.85:  return "Expert"
        if c >= 0.70:  return "Proficient"
        if c >= 0.55:  return "Developing"
        if c >= 0.35:  return "Beginner"
        return "Critical Gap"

    def to_dict(self) -> dict:
        return {
            "domain":             self.domain,
            "confidence":         round(self.confidence, 4),
            "attempts":           self.attempts,
            "successes":          self.successes,
            "success_rate":       round(self.success_rate, 4),
            "learning_velocity":  round(self.learning_velocity, 4),
            "last_used":          self.last_used,
            "weaknesses":         self.weaknesses,
            "notes":              self.notes,
            "confidence_label":   self.confidence_label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SkillProfile":
        d = dict(d)
        d.pop("success_rate", None)       # computed property, not stored
        d.pop("confidence_label", None)   # computed property, not stored
        return cls(**d)


class SkillMemory:
    """
    Registry of all SkillProfiles with JSON persistence.

    Thread-safe. All writes immediately flush to disk.

    Usage
    -----
        sm = SkillMemory()
        sm.record_attempt("python", succeeded=True, confidence_delta=0.05)
        profile = sm.get("python")
        print(sm.summary_table())
    """

    def __init__(self, path: str = _DEFAULT_PATH):
        self._path: str = path
        self._lock: Lock = Lock()
        self._profiles: Dict[str, SkillProfile] = self._load()

    # ------------------------------------------------------------------
    # Public — write
    # ------------------------------------------------------------------

    def record_attempt(
        self,
        domain: str,
        succeeded: bool,
        confidence_delta: float = 0.0,
    ) -> SkillProfile:
        """
        Record one skill attempt and update the profile.

        Parameters
        ----------
        domain : str
            The skill domain exercised.
        succeeded : bool
            Whether the attempt succeeded.
        confidence_delta : float
            Signed confidence change from the Reflection Engine.

        Returns
        -------
        SkillProfile
            Updated profile for the domain.
        """
        with self._lock:
            profile = self._get_or_create(domain)
            profile.attempts  += 1
            if succeeded:
                profile.successes += 1

            # Update confidence (clamp)
            profile.confidence = max(0.0, min(1.0, profile.confidence + confidence_delta))

            # Update learning velocity using EMA
            # velocity = rate of confidence change, scaled to per-10-attempts
            velocity_sample = confidence_delta * 10
            profile.learning_velocity = (
                _VELOCITY_ALPHA * velocity_sample
                + (1 - _VELOCITY_ALPHA) * profile.learning_velocity
            )

            # Timestamp
            profile.last_used = datetime.now(timezone.utc).isoformat()

            self._save()
            return profile

    def add_weakness(self, domain: str, weakness: str) -> SkillProfile:
        """
        Add an identified weakness to a domain's profile.
        Duplicates are ignored (case-insensitive).
        """
        with self._lock:
            profile = self._get_or_create(domain)
            lower_existing = [w.lower() for w in profile.weaknesses]
            if weakness.lower() not in lower_existing:
                profile.weaknesses.append(weakness)
            self._save()
            return profile

    def set_notes(self, domain: str, notes: str) -> SkillProfile:
        """Set free-form notes for a domain."""
        with self._lock:
            profile = self._get_or_create(domain)
            profile.notes = notes
            self._save()
            return profile

    # ------------------------------------------------------------------
    # Public — read
    # ------------------------------------------------------------------

    def get(self, domain: str) -> Optional[SkillProfile]:
        """Return the profile for a domain, or None if not yet tracked."""
        with self._lock:
            return self._profiles.get(domain)

    def get_or_default(self, domain: str) -> SkillProfile:
        """Return the profile for a domain, creating a default if missing."""
        with self._lock:
            return self._get_or_create(domain)

    def all_profiles(self) -> List[SkillProfile]:
        """Return all tracked profiles sorted by confidence descending."""
        with self._lock:
            return sorted(self._profiles.values(), key=lambda p: p.confidence, reverse=True)

    def weakest_skills(self, n: int = 5) -> List[SkillProfile]:
        """Return the n lowest-confidence skills."""
        with self._lock:
            return sorted(self._profiles.values(), key=lambda p: p.confidence)[:n]

    def strongest_skills(self, n: int = 5) -> List[SkillProfile]:
        """Return the n highest-confidence skills."""
        with self._lock:
            return sorted(self._profiles.values(), key=lambda p: p.confidence, reverse=True)[:n]

    def summary_table(self) -> str:
        """
        Return a human-readable ASCII table of all skill profiles.

        Example output:
            Domain          | Confidence | Level       | Attempts | Success% | Velocity
            translation     | 65%        | Developing  | 12       | 83.3%    | +0.04
            rf_systems      | 44%        | Beginner    | 5        |  40.0%   | -0.08
        """
        profiles = self.all_profiles()
        if not profiles:
            return "No skills tracked yet."

        header = (
            f"{'Domain':<20} | {'Conf':>5} | {'Level':<12} | "
            f"{'Tries':>5} | {'Win%':>6} | {'Velocity':>9}"
        )
        sep = "-" * len(header)
        rows = [header, sep]

        for p in profiles:
            sr  = f"{p.success_rate*100:5.1f}%" if p.success_rate >= 0 else "  N/A "
            vel = f"{p.learning_velocity:+.3f}"
            rows.append(
                f"{p.domain:<20} | {p.confidence*100:4.0f}% | {p.confidence_label:<12} | "
                f"{p.attempts:>5} | {sr:>6} | {vel:>9}"
            )
        return "\n".join(rows)

    def count(self) -> int:
        with self._lock:
            return len(self._profiles)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _get_or_create(self, domain: str) -> SkillProfile:
        """Must be called under self._lock."""
        if domain not in self._profiles:
            self._profiles[domain] = SkillProfile(domain=domain)
        return self._profiles[domain]

    def _load(self) -> Dict[str, SkillProfile]:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return {
                k: SkillProfile.from_dict(v)
                for k, v in data.items()
                if isinstance(v, dict)
            }
        except (json.JSONDecodeError, TypeError):
            return {}

    def _save(self) -> None:
        """Must be called under self._lock."""
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(
                    {k: v.to_dict() for k, v in self._profiles.items()},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except OSError:
            pass  # Non-fatal
