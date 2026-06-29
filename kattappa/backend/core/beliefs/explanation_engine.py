"""Belief Management Component 8: Explanation Engine.

Generates human-readable trace explanations justifying active belief states
using provenance, evidence, and parent-child dependencies.
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from backend.core.beliefs.belief import Belief
from backend.core.beliefs.belief_store import BeliefStore
from backend.core.provenance.coordinator import ProvenanceCoordinator


class ExplanationEngine:
    """Recursively resolves dependencies to explain why or why not a belief is held."""

    def __init__(self, store: BeliefStore) -> None:
        self._store = store
        self._prov = ProvenanceCoordinator.get_instance()

    def explain_belief(self, belief_id: str) -> str:
        """Compiles a complete human-readable trace explanation justifying a belief."""
        belief = self._store.get_belief(belief_id)
        if not belief:
            return f"No belief found with ID {belief_id}."

        lines = [
            f"### Justification for belief: {belief.claim_subject}.{belief.claim_predicate} = '{belief.claim_value}'",
            f"- **Confidence**: {belief.confidence:.2f}",
            f"- **Status**: {belief.truth_status.value}",
            f"- **Version**: {belief.version}",
            "- **Timeline validity**: "
            f"from {datetime.datetime.fromtimestamp(belief.valid_from, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
            + (
                f" to {datetime.datetime.fromtimestamp(belief.valid_until, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                if belief.valid_until
                else " (current/indefinite)"
            ),
        ]

        # 1. Fetch justifications and evidence items
        justifications = self._store.get_justifications_for_belief(belief_id)
        if justifications:
            lines.append("- **Rationales**:")
            for j in justifications:
                lines.append(f"  * {j.rationale}")

        evidence_list = self._prov.kg.get_evidence_for_target(belief.claim_subject)
        if evidence_list:
            lines.append("- **Supporting Evidence items**:")
            for ev in evidence_list:
                if ev.evidence_id in belief.evidence_ids:
                    src = self._prov.sources.get_source(ev.source_id)
                    src_name = src.name if src else ev.source_id
                    lines.append(
                        f"  * [{ev.evidence_level.name}] Sourced from '{src_name}' (confidence: {ev.confidence:.2f}) "
                        + (f"ref: {ev.context_citation}" if ev.context_citation else "")
                    )

        # 2. Trace parent belief dependencies
        parents = self._store.get_parent_dependencies(belief_id)
        if parents:
            lines.append("- **Derived from parent beliefs**:")
            for p in parents:
                parent_belief = self._store.get_belief(p.parent_belief_id)
                if parent_belief:
                    lines.append(
                        f"  * {parent_belief.claim_subject}.{parent_belief.claim_predicate} = "
                        f"'{parent_belief.claim_value}' (parent_id: {p.parent_belief_id})"
                    )

        return "\n".join(lines)

    def explain_why_not(self, subject: str, predicate: str, target_value: Any) -> str:
        """Explains why the system does not hold a target belief value."""
        belief = self._store.get_belief_by_claim(subject, predicate)
        if not belief:
            return f"No active belief exists for {subject}.{predicate}."

        if belief.claim_value == target_value:
            return (
                f"Actually, the system believes {subject}.{predicate} is '{target_value}' "
                f"(status: {belief.truth_status.value}, confidence: {belief.confidence:.2f})."
            )

        explanation = [
            f"### Refuted: {subject}.{predicate} is NOT '{target_value}'",
            f"- **Active Belief**: '{belief.claim_value}' (confidence: {belief.confidence:.2f})",
            f"- **Conflict details**: The system holds the active belief value instead because it is supported by stronger/prior evidence.",
        ]
        
        return "\n".join(explanation)
