"""Proposal Engine (Layer 10/11 - Step 6 Research & Self-Improvement).

Decides, researches, and recommends optimization proposals.
Kattappa can suggest improvements but can never grant itself authority,
modify its own guardrails, or deploy itself. Every production change requires
independent evidence, human approval, and a rollback path.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


class ProposalStatus(str, Enum):
    PENDING = "pending"
    SANDBOX_APPROVED = "sandbox_approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


def _proposals_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "proposals.json"


def _negative_knowledge_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "negative_knowledge.json"


class ProposalEngine:
    PROTECTED_CORE = {
        "validators",
        "policy_engine",
        "consensus_engine",
        "value_engine",
        "benchmark_arena",
        "approval_gates",
        "deployment_controls",
        "reliability",
        "execution_policy",
        "main.py",
    }

    # -- 1. Observation Engine ---------------------------------------------
    @classmethod
    def observe_issue(cls, issue: str, severity: str, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        """Logs factual observation of issues without root cause analysis."""
        return {
            "observation_id": f"obs_{int(time.time())}",
            "issue": issue,
            "severity": severity,
            "metrics": metrics or {},
            "timestamp": time.time(),
        }

    # -- 2. Reflection Hypotheses -------------------------------------------
    @classmethod
    def reflect_on_observation(cls, observation: dict[str, Any]) -> list[dict[str, Any]]:
        """Generates hypotheses about why the issue occurred. Proposes NO code changes."""
        issue_lower = observation.get("issue", "").lower()
        hypotheses = []

        if "latency" in issue_lower or "speed" in issue_lower:
            hypotheses.append({
                "hypothesis": "Capability Graph lookup complexity or database indexing latency increased.",
                "confidence": 0.75,
            })
            hypotheses.append({
                "hypothesis": "Subprocess overhead in sandboxed verification loops is causing delay.",
                "confidence": 0.60,
            })
        elif "error" in issue_lower or "failure" in issue_lower:
            hypotheses.append({
                "hypothesis": "A missing validator constraint check is causing exception cascades.",
                "confidence": 0.80,
            })
        else:
            hypotheses.append({
                "hypothesis": "General optimization potential in the system topology.",
                "confidence": 0.50,
            })

        return hypotheses

    # -- 3. Protected Core Guardrail ---------------------------------------
    @classmethod
    def is_protected_core_violation(cls, proposal_text: str) -> bool:
        """Returns True if proposal text mentions modifying any protected modules."""
        proposal_lower = proposal_text.lower()
        # Checks namespace / files
        for core_module in cls.PROTECTED_CORE:
            if core_module in proposal_lower:
                return True
        return False

    # -- 4. Negative-Knowledge Check ---------------------------------------
    @classmethod
    def negative_knowledge_exists(cls, title: str) -> bool:
        """Returns True if the proposed concept/title matches historical failures."""
        path = _negative_knowledge_path()
        if not path.exists():
            return False
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                return False
            title_lower = title.lower().strip()
            for entry in entries:
                if entry.get("title", "").lower().strip() == title_lower:
                    return True
        except Exception:
            pass
        return False

    @classmethod
    def register_negative_knowledge(cls, title: str, reason: str) -> dict[str, Any]:
        """Appends a known failure pattern to the negative knowledge store."""
        path = _negative_knowledge_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        entries = []
        if path.exists():
            try:
                entries = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(entries, list):
                    entries = []
            except Exception:
                pass

        new_entry = {
            "title": title,
            "reason": reason,
            "logged_at": time.time(),
        }
        entries.append(new_entry)
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        return new_entry

    # -- 5. Occam Gate Comparison ------------------------------------------
    @classmethod
    def evaluate_occam_gate(
        cls, proposal: str, expected_gain: float, complexity: int
    ) -> dict[str, Any]:
        """Forces proposal to justify itself against a simple config/caching fix."""
        # Simple fix candidate defaults
        simple_fix = "Apply config change or cache layer instead of full redesign."
        simple_complexity = 2
        simple_expected_gain = expected_gain * 0.70  # Assumes simple fix yields 70% of candidate's gain

        # ROI = expected_gain / complexity
        candidate_roi = expected_gain / max(1, complexity)
        simple_roi = simple_expected_gain / simple_complexity

        beats_simple = candidate_roi >= simple_roi

        return {
            "simple_fix_alternative": simple_fix,
            "candidate_roi": round(candidate_roi, 4),
            "simple_roi": round(simple_roi, 4),
            "beats_simple_fix": beats_simple,
        }

    # -- 6. Proposal Creation & Storage ------------------------------------
    @classmethod
    def create_proposal(
        cls,
        title: str,
        problem: str,
        evidence: str,
        proposal: str,
        expected_gain: float,
        complexity: int,
        confidence: int,
    ) -> dict[str, Any]:
        """Validates safety, Negative Knowledge, and Occam Gate before writing proposal."""
        # 1. Protected Core Check
        if cls.is_protected_core_violation(proposal) or cls.is_protected_core_violation(title):
            return {
                "id": f"prop_rejected_{int(time.time())}",
                "title": title,
                "status": ProposalStatus.REJECTED.value,
                "reasons": ["Attempts to modify or override protected core modules."],
            }

        # 2. Negative Knowledge Check
        if cls.negative_knowledge_exists(title):
            return {
                "id": f"prop_rejected_{int(time.time())}",
                "title": title,
                "status": ProposalStatus.REJECTED.value,
                "reasons": ["This proposal matches a known failure pattern in the Negative-Knowledge Repository."],
            }

        # 3. Occam Gate Check
        occam_res = cls.evaluate_occam_gate(proposal, expected_gain, complexity)
        if not occam_res["beats_simple_fix"]:
            return {
                "id": f"prop_rejected_{int(time.time())}",
                "title": title,
                "status": ProposalStatus.REJECTED.value,
                "reasons": [
                    f"Rejected by Occam Gate. Simple alternative ROI ({occam_res['simple_roi']}) "
                    f"beats complex proposal ROI ({occam_res['candidate_roi']})."
                ],
                "occam_gate": occam_res,
            }

        # Save to persistent storage
        path = _proposals_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        history = []
        if path.exists():
            try:
                history = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(history, list):
                    history = []
            except Exception:
                pass

        new_proposal = {
            "id": f"prop_{int(time.time())}",
            "title": title,
            "problem": problem,
            "evidence": evidence,
            "proposal": proposal,
            "expected_gain": expected_gain,
            "complexity": complexity,
            "confidence": confidence,
            "occam_gate": occam_res,
            "status": ProposalStatus.PENDING.value,
            "created_at": time.time(),
        }

        history.append(new_proposal)
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")

        return new_proposal

    @classmethod
    def list_proposals(cls) -> list[dict[str, Any]]:
        """Loads all proposals."""
        path = _proposals_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    @classmethod
    def transition_status(cls, proposal_id: str, new_status: ProposalStatus) -> dict[str, Any]:
        """Modifies proposal status (representing Human Gates 1 or 2)."""
        path = _proposals_path()
        if not path.exists():
            raise KeyError("No proposals registered yet")

        history = []
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raise KeyError("Failed to parse proposals database")

        target = None
        for prop in history:
            if prop.get("id") == proposal_id:
                prop["status"] = new_status.value
                prop["updated_at"] = time.time()
                target = prop
                break

        if target is None:
            raise KeyError(f"Proposal {proposal_id} not found")

        path.write_text(json.dumps(history, indent=2), encoding="utf-8")
        return target
