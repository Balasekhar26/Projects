"""
Step 10.0 — Source Trust Engine.
Manages research publication trust levels, consensus scores, and reputation dynamics.
"""
from __future__ import annotations

import json
import threading
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.logger import log_event


class TrustLevel(str, Enum):
    VERIFIED = "VERIFIED"     # Peer reviewed / official
    HIGH = "HIGH"             # Major technical source
    MEDIUM = "MEDIUM"         # Industry blog
    LOW = "LOW"               # Forum / unknown
    REJECTED = "REJECTED"     # Hallucination risk / low reputation


def _reputation_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "source_reputation.json"


class SourceTrustEngine:
    _lock = threading.RLock()

    @classmethod
    def load_reputations(cls) -> dict[str, dict[str, Any]]:
        with cls._lock:
            path = _reputation_path()
            if not path.exists():
                return {}
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}

    @classmethod
    def save_reputations(cls, reputations: dict[str, dict[str, Any]]) -> None:
        with cls._lock:
            path = _reputation_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(reputations, indent=2), encoding="utf-8")

    @classmethod
    def get_source_reputation(cls, source_name: str, source_type: str | None = None) -> dict[str, Any]:
        """Gets or initializes the reputation stats for a source."""
        with cls._lock:
            reps = cls.load_reputations()
            
            clean_name = source_name.strip()
            if clean_name in reps:
                return reps[clean_name]

            # Determine initial trust level and base score
            st = str(source_type).strip().lower() if source_type else ""
            if "peer" in st or "verified" in st:
                level = TrustLevel.VERIFIED
                base_score = 1.0
            elif "reproduced" in st or "high" in st:
                level = TrustLevel.HIGH
                base_score = 0.8
            elif "preprint" in st or "medium" in st:
                level = TrustLevel.MEDIUM
                base_score = 0.6
            elif "blog" in st or "low" in st:
                level = TrustLevel.LOW
                base_score = 0.3
            else:
                level = TrustLevel.LOW
                base_score = 0.3

            entry = {
                "source_name": clean_name,
                "trust_level": level.value,
                "correct_predictions": 0,
                "incorrect_predictions": 0,
                "useful_ideas": 0,
                "rejected_ideas": 0,
                "reputation_score": base_score,
                "base_score": base_score
            }
            reps[clean_name] = entry
            cls.save_reputations(reps)
            return entry

    @classmethod
    def calculate_consensus(cls, sources: list[str]) -> float:
        """Computes the combined consensus score across multiple sources for a claim."""
        with cls._lock:
            if not sources:
                return 0.0
            
            reps = []
            for src in sources:
                rep_data = cls.get_source_reputation(src)
                if rep_data.get("trust_level") == TrustLevel.REJECTED.value:
                    continue  # Ignore rejected sources in consensus
                reps.append(rep_data.get("reputation_score", 0.3))

            if not reps:
                return 0.0
            if len(reps) == 1:
                return reps[0]

            # Multi-source combined probability: 1 - product(1 - rep)
            prod = 1.0
            for r in reps:
                prod *= (1.0 - r)
            return round(1.0 - prod, 4)

    @classmethod
    def update_reputation_for_source(cls, source_name: str, outcome: str) -> None:
        """Updates reputation metrics for a specific source name."""
        with cls._lock:
            reps = cls.load_reputations()
            clean_name = source_name.strip()
            if clean_name not in reps:
                # Initialize it
                cls.get_source_reputation(clean_name)
                reps = cls.load_reputations()

            entry = reps[clean_name]
            
            outcome_clean = outcome.upper()
            if outcome_clean == "DEPLOYED_SUCCESSFUL":
                entry["correct_predictions"] += 1
                entry["useful_ideas"] += 1
            elif outcome_clean in ("DEPLOYED_FAILED", "ROLLBACK"):
                entry["incorrect_predictions"] += 1
            elif outcome_clean in ("REJECTED", "SANDBOX_FAILED", "BENCHMARK_FAILED"):
                entry["rejected_ideas"] += 1
            elif outcome_clean == "APPROVED":
                entry["useful_ideas"] += 1

            # Recalculate reputation score
            base = entry.get("base_score", 0.3)
            useful = entry["useful_ideas"]
            rejected = entry["rejected_ideas"]
            correct = entry["correct_predictions"]
            incorrect = entry["incorrect_predictions"]

            new_score = base + 0.05 * useful - 0.05 * rejected + 0.10 * correct - 0.10 * incorrect
            new_score = max(0.0, min(1.0, new_score))
            entry["reputation_score"] = round(new_score, 4)

            # Check if trust level degrades or upgrades
            if new_score < 0.20:
                entry["trust_level"] = TrustLevel.REJECTED.value
            elif new_score >= 0.85:
                entry["trust_level"] = TrustLevel.VERIFIED.value
            elif new_score >= 0.70:
                entry["trust_level"] = TrustLevel.HIGH.value
            elif new_score >= 0.50:
                entry["trust_level"] = TrustLevel.MEDIUM.value
            else:
                entry["trust_level"] = TrustLevel.LOW.value

            reps[clean_name] = entry
            cls.save_reputations(reps)
            log_event(f"source_trust_engine: updated source '{clean_name}' reputation to {new_score:.4f} ({entry['trust_level']})")

    @classmethod
    def update_reputation(cls, proposal_id: str, outcome: str) -> None:
        """Looks up the proposal by ID to find its source, and updates its reputation."""
        from backend.core.proposal_engine import ProposalEngine
        proposals = ProposalEngine.list_proposals()
        for p in proposals:
            if p.get("id") == proposal_id:
                src_name = p.get("source_name")
                if src_name:
                    cls.update_reputation_for_source(src_name, outcome)
                break
