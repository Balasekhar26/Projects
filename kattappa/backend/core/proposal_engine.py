"""Proposal Engine (Layer 10/11 - Step 6 Research & Self-Improvement).

Decides, researches, and recommends optimization proposals.
Kattappa can suggest improvements but can never grant itself authority,
modify its own guardrails, or deploy itself. Every production change requires
independent evidence, human approval, and a rollback path.
"""

from __future__ import annotations

import json
import math
import time
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root
from backend.core.proposal_governance import ProposalStatus


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
        "reliability_monitor",
        "proposal_governance",
        "approval_gates",
        "deployment_controls",
        "deployment_controller",
        "reliability",
        "execution_policy",
        "main.py",
    }

    VALID_TRANSITIONS = {
        ProposalStatus.DRAFT: {ProposalStatus.PENDING, ProposalStatus.EXPIRED, ProposalStatus.ARCHIVED},
        ProposalStatus.PENDING: {ProposalStatus.APPROVED_GATE_1, ProposalStatus.REJECTED, ProposalStatus.NEEDS_REVISION, ProposalStatus.EXPIRED, ProposalStatus.ARCHIVED, ProposalStatus.SANDBOX_APPROVED},
        ProposalStatus.NEEDS_REVISION: {ProposalStatus.PENDING, ProposalStatus.ARCHIVED},
        ProposalStatus.APPROVED_GATE_1: {ProposalStatus.LAB_TESTING, ProposalStatus.REJECTED, ProposalStatus.EXPIRED, ProposalStatus.ARCHIVED},
        ProposalStatus.SANDBOX_APPROVED: {ProposalStatus.LAB_TESTING, ProposalStatus.REJECTED, ProposalStatus.EXPIRED, ProposalStatus.ARCHIVED},
        ProposalStatus.LAB_TESTING: {ProposalStatus.BENCHMARKING, ProposalStatus.REJECTED, ProposalStatus.EXPIRED, ProposalStatus.ARCHIVED},
        ProposalStatus.BENCHMARKING: {ProposalStatus.APPROVED_GATE_2, ProposalStatus.REJECTED, ProposalStatus.EXPIRED, ProposalStatus.ARCHIVED},
        ProposalStatus.APPROVED_GATE_2: {ProposalStatus.CANARY, ProposalStatus.REJECTED, ProposalStatus.EXPIRED, ProposalStatus.ARCHIVED},
        ProposalStatus.CANARY: {ProposalStatus.DEPLOYED, ProposalStatus.REJECTED, ProposalStatus.EXPIRED, ProposalStatus.ARCHIVED},
        ProposalStatus.DEPLOYED: {ProposalStatus.ARCHIVED},
        ProposalStatus.EXPIRED: {ProposalStatus.ARCHIVED},
        ProposalStatus.REJECTED: {ProposalStatus.ARCHIVED},
        ProposalStatus.ARCHIVED: set(),
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
        for core_module in cls.PROTECTED_CORE:
            if core_module in proposal_lower:
                return True
        return False

    # -- 4. Negative-Knowledge Check ---------------------------------------
    @classmethod
    def negative_knowledge_exists(cls, title: str) -> bool:
        """Returns True if the proposed concept/title matches historical failures semantically
        and the entry has not decayed/expired.
        """
        path = _negative_knowledge_path()
        if not path.exists():
            return False
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                return False
            
            # Filter entries by applying confidence decay
            active_entries = []
            now = time.time()
            decay_rate_per_day = 0.05
            
            for entry in entries:
                logged_at = entry.get("logged_at", 0.0)
                days_elapsed = (now - logged_at) / 86400.0
                base_conf = entry.get("confidence", 1.0)
                current_conf = base_conf * math.exp(-decay_rate_per_day * days_elapsed)
                
                if current_conf >= 0.3:
                    entry_copy = dict(entry)
                    entry_copy["confidence"] = current_conf
                    active_entries.append(entry_copy)

            if not active_entries:
                return False

            from backend.core.proposal_governance import SemanticNegativeKnowledgeMatcher
            band, _, _ = SemanticNegativeKnowledgeMatcher.check_semantic_duplicate(title, active_entries)
            return band == "block"
        except Exception:
            return False

    @classmethod
    def register_negative_knowledge(cls, title: str, reason: str, confidence: float = 1.0) -> dict[str, Any]:
        """Appends a known failure pattern to the negative knowledge store with confidence score."""
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
            "confidence": confidence,
            "logged_at": time.time(),
        }
        entries.append(new_entry)
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        return new_entry

    # -- 5. Occam Gate & Skepticism Filter ----------------------------------
    @classmethod
    def apply_skepticism_filter(cls, expected_gain: float) -> tuple[float, float]:
        """Caps/downgrades expected gain using historical distributions and returns (skeptical_gain, novelty_risk_score)."""
        from backend.core.proposal_governance import TrackRecordStore
        records = TrackRecordStore.get_track_records()
        gains = []
        for r in records:
            prod = r.get("production_result")
            if prod and prod.get("success"):
                metrics = prod.get("metrics", {})
                gain = metrics.get("gain")
                if isinstance(gain, (int, float)):
                    gains.append(float(gain))
        
        # default stats if no history
        mean = 5.0
        std_dev = 2.0
        
        if len(gains) >= 3:
            mean = sum(gains) / len(gains)
            variance = sum((x - mean) ** 2 for x in gains) / len(gains)
            std_dev = math.sqrt(variance) if variance > 0 else 1.0

        if expected_gain > mean:
            z_score = (expected_gain - mean) / std_dev
            novelty_risk_score = min(100.0, max(0.0, z_score * 20.0))
        else:
            novelty_risk_score = 0.0

        limit = mean + 2 * std_dev
        skeptical_gain = expected_gain
        if expected_gain > limit:
            skeptical_gain = limit
            
        return skeptical_gain, novelty_risk_score

    @classmethod
    def evaluate_occam_gate(
        cls, proposal: str, expected_gain: float, complexity: int
    ) -> dict[str, Any]:
        """Forces proposal to justify itself against a simple config/caching fix."""
        # Simple fix candidate defaults
        simple_fix = "Apply config change or cache layer instead of full redesign."
        simple_complexity = 2
        
        # Apply skepticism filter to expectations
        skeptical_gain, novelty_risk_score = cls.apply_skepticism_filter(expected_gain)
        simple_expected_gain = skeptical_gain * 0.70  # Assumes simple fix yields 70% of candidate's gain

        # ROI = expected_gain / complexity
        candidate_roi = skeptical_gain / max(1, complexity)
        simple_roi = simple_expected_gain / simple_complexity

        beats_simple = candidate_roi >= simple_roi

        return {
            "simple_fix_alternative": simple_fix,
            "candidate_roi": round(candidate_roi, 4),
            "simple_roi": round(simple_roi, 4),
            "beats_simple_fix": beats_simple,
            "original_expected_gain": expected_gain,
            "skeptical_gain": round(skeptical_gain, 4),
            "downgraded": skeptical_gain < expected_gain,
            "novelty_risk_score": round(novelty_risk_score, 2),
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
        affected_modules: list[str] | None = None,
        parent_proposal_id: str | None = None,
        research_cost: float = 10.0,
    ) -> dict[str, Any]:
        """Validates safety, budget, Negative Knowledge, and Occam Gate before writing proposal."""
        if affected_modules is None:
            affected_modules = []

        from backend.core.proposal_governance import (
            ProtectedCoreRegistry,
            ProposalIntegrityScorer,
            ProposalBudgetManager,
            SemanticNegativeKnowledgeMatcher
        )

        # 1. Protected Core & Integrity check
        pis = ProposalIntegrityScorer.compute_pis(title, proposal, affected_modules)
        if pis < 100.0 or ProtectedCoreRegistry.check_affected_modules(affected_modules) or cls.is_protected_core_violation(proposal) or cls.is_protected_core_violation(title):
            return {
                "id": f"prop_rejected_{int(time.time())}",
                "title": title,
                "status": ProposalStatus.REJECTED.value,
                "reasons": ["Attempts to modify or override protected core modules or governance pathways (Integrity Violation)."],
                "pis": pis
            }

        # 2. Daily Proposal Budget Check
        limit = ProposalBudgetManager.get_budget_limit()
        now = time.time()
        day_ago = now - 86400
        created_today = sum(1 for p in cls.list_proposals() if p.get("created_at", 0.0) >= day_ago)
        if created_today >= limit:
            return {
                "id": f"prop_rejected_{int(time.time())}",
                "title": title,
                "status": ProposalStatus.REJECTED.value,
                "reasons": [
                    f"Proposal budget exceeded for the day. Daily limit: {limit}, active proposals created: {created_today}."
                ],
            }

        # 3. Negative Knowledge & Confidence Bands Check
        path = _negative_knowledge_path()
        entries = []
        if path.exists():
            try:
                entries = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        band, score, reason = SemanticNegativeKnowledgeMatcher.check_semantic_duplicate(title, entries)
        
        # Determine status and warnings from the band
        status = ProposalStatus.PENDING.value
        reasons = []
        warnings = []
        
        if band == "block":
            return {
                "id": f"prop_rejected_{int(time.time())}",
                "title": title,
                "status": ProposalStatus.REJECTED.value,
                "reasons": [f"This proposal matches a known failure pattern in the Negative-Knowledge Repository: {reason}"],
                "similarity": score,
            }
        elif band == "review":
            status = ProposalStatus.NEEDS_REVISION.value
            reasons = [f"Requires Human Review due to high similarity to a past failure: {reason}"]
        elif band == "warning":
            warnings = [f"Warning: Moderate similarity to past failure: {reason}"]

        # 4. Occam Gate Check
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

        history = cls.list_proposals()

        new_proposal = {
            "id": f"prop_{int(time.time())}",
            "title": title,
            "problem": problem,
            "evidence": evidence,
            "proposal": proposal,
            "expected_gain": expected_gain,
            "complexity": complexity,
            "confidence": confidence,
            "affected_modules": affected_modules,
            "parent_proposal_id": parent_proposal_id,
            "research_cost": research_cost,
            "occam_gate": occam_res,
            "status": status,
            "reasons": reasons,
            "warnings": warnings,
            "pis": pis,
            "created_at": time.time(),
        }

        history.append(new_proposal)
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")

        try:
            from backend.core.proposal_governance import ImprovementRegistry
            ImprovementRegistry.register_or_update(new_proposal["id"], proposal_dict=new_proposal)
        except Exception:
            pass

        return new_proposal

    @classmethod
    def list_proposals(cls) -> list[dict[str, Any]]:
        """Loads all proposals and dynamically processes expirations."""
        path = _proposals_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            
            # Clean and expire stale ones
            from backend.core.proposal_governance import ProposalExpirationManager
            updated = ProposalExpirationManager.expire_stale_proposals(data)
            path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
            return updated
        except Exception:
            return []

    @classmethod
    def transition_status(cls, proposal_id: str, new_status: ProposalStatus) -> dict[str, Any]:
        """Modifies proposal status representing Gate reviews or lab execution."""
        history = cls.list_proposals()
        if not history:
            raise KeyError("No proposals registered yet")

        target = None
        for prop in history:
            if prop.get("id") == proposal_id:
                # Validate lifecycle state transition
                current_status_str = prop.get("status", ProposalStatus.PENDING.value)
                try:
                    current_status = ProposalStatus(current_status_str)
                except ValueError:
                    current_status = ProposalStatus.PENDING

                valid_next_states = cls.VALID_TRANSITIONS.get(current_status, set())
                if new_status not in valid_next_states:
                    raise ValueError(f"Invalid transition from {current_status.value} to {new_status.value}")

                prop["status"] = new_status.value
                prop["updated_at"] = time.time()
                target = prop
                break

        if target is None:
            raise KeyError(f"Proposal {proposal_id} not found")

        path = _proposals_path()
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")

        try:
            from backend.core.proposal_governance import ImprovementRegistry
            ImprovementRegistry.register_or_update(proposal_id, proposal_dict=target)
        except Exception:
            pass

        return target
