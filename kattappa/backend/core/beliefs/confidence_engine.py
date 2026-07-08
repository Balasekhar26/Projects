"""Belief Management Component 5: Confidence Engine.

Aggregates confidence scores from Provenance Store evidence items,
relying on the rules defined in TrustEngine.
"""
from __future__ import annotations

import logging
from typing import List

from backend.core.provenance.coordinator import ProvenanceCoordinator
from backend.core.provenance.models import ProvenanceEvidenceItem
from backend.core.trust_evidence import TrustEngine, EvidenceItem

logger = logging.getLogger(__name__)


class ConfidenceEngine:
    """Aggregates and computes belief confidence scores based on provenance evidence."""

    @staticmethod
    def calculate_confidence(evidence_list: List[ProvenanceEvidenceItem], statement: str = "claim") -> float:
        """Invokes TrustEngine to calculate the composite confidence score.

        Converts ProvenanceEvidenceItem objects to EvidenceItem format first.
        """
        if not evidence_list:
            return 0.3  # Default fallback uncertainty score

        # Map to trust_evidence.EvidenceItem
        mapped_evidence = []
        for ev in evidence_list:
            mapped_evidence.append(
                EvidenceItem(
                    source=ev.source_id,
                    level=ev.evidence_level,
                    supports=ev.supports,
                    detail=ev.context_citation,
                )
            )

        report = TrustEngine.assess(statement, mapped_evidence)
        return report.evidence_score
