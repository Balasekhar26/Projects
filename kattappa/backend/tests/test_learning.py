"""Unit and integration tests for Program 7: Learning & Memory Update Framework.
"""
from __future__ import annotations

import pytest

from backend.core.learning.models import CandidateStatus
from backend.core.learning.confidence import ConfidenceEngine
from backend.core.learning.conflict import ConflictDetector
from backend.core.learning.safety import SafetyPolicyEngine
from backend.core.learning.consolidator import MemoryConsolidator
from backend.core.learning.learning_engine import LearningEngine
from backend.core.reflection.models import LearningCandidate


def test_confidence_engine_evidence_calculations():
    """Verifies that confidence scores scale cleanly based on observation frequencies."""
    # Count 1: 1 - 0.75^1 = 0.25
    assert ConfidenceEngine.calculate_score(1) == 0.25
    # Count 5: 1 - 0.75^5 = 0.763
    assert ConfidenceEngine.calculate_score(5) == 0.763
    # Count 20: 1 - 0.75^20 = 0.997
    assert ConfidenceEngine.calculate_score(20) == 0.997
    assert ConfidenceEngine.calculate_score(0) == 0.0


def test_conflict_detection():
    """Verifies that opposing policy updates targeting same variables raise conflicts."""
    cand1 = LearningCandidate(
        candidate_id="c1",
        target_type="RetryLimit",
        explanation="Increase retries",
        proposed_update={"max_retries": 5},
    )
    cand2 = LearningCandidate(
        candidate_id="c2",
        target_type="RetryLimit",
        explanation="Decrease retries",
        proposed_update={"max_retries": 2},
    )
    cand3 = LearningCandidate(
        candidate_id="c3",
        target_type="RetryLimit",
        explanation="Same retries config",
        proposed_update={"max_retries": 5},
    )

    conflicts = ConflictDetector.detect_conflicts(cand1, [cand2])
    assert len(conflicts) == 1
    assert conflicts[0].candidate_id == "c2"

    # Same target/value is not a conflict
    assert len(ConflictDetector.detect_conflicts(cand1, [cand3])) == 0


def test_safety_filter_blocking_protected_updates():
    """Verifies SafetyPolicyEngine quenches automatic apply on protected variables."""
    # Safe candidate (high confidence, non-sensitive variables)
    cand_safe = LearningCandidate(
        candidate_id="c_safe",
        target_type="ToolPolicy",
        explanation="Cache tool outcomes",
        proposed_update={"cache_results": True},
        confidence=0.85,
    )
    # Unsafe candidate (attempts to overwrite authentication parameters)
    cand_unsafe = LearningCandidate(
        candidate_id="c_unsafe",
        target_type="ConstraintRule",
        explanation="Bypass auth bounds",
        proposed_update={"verify_permissions_preflight": True},
        confidence=0.90,
    )
    # Low confidence candidate
    cand_low_conf = LearningCandidate(
        candidate_id="c_low",
        target_type="ToolPolicy",
        explanation="Cache tool outcomes",
        proposed_update={"cache_results": True},
        confidence=0.60,
    )

    assert SafetyPolicyEngine.is_safe_to_auto_apply(cand_safe) is True
    assert SafetyPolicyEngine.is_safe_to_auto_apply(cand_unsafe) is False
    assert SafetyPolicyEngine.is_safe_to_auto_apply(cand_low_conf) is False


def test_memory_consolidation_and_version_rollbacks():
    """Verifies consolidator updates active config state and reverts changes on rollbacks."""
    consolidator = MemoryConsolidator()
    assert consolidator.active_config["max_retries"] == 3

    cand = LearningCandidate(
        candidate_id="c_lim",
        target_type="RetryLimit",
        explanation="Bump retry limits",
        proposed_update={"max_retries": 5, "backoff_policy": "exponential"},
    )

    version = consolidator.consolidate(cand)
    assert consolidator.active_config["max_retries"] == 5
    assert consolidator.active_config["backoff_policy"] == "exponential"
    assert len(consolidator.versions) == 1

    # Roll back
    success = consolidator.rollback(version.version_id)
    assert success is True
    assert consolidator.active_config["max_retries"] == 3
    assert consolidator.active_config["backoff_policy"] == "linear"


def test_learning_engine_approval_pipeline():
    """Verifies that submitted candidates can be auto-applied or manually approved/rejected."""
    engine = LearningEngine()

    cand = LearningCandidate(
        candidate_id="c_app",
        target_type="ToolPolicy",
        explanation="Cache results to save time",
        proposed_update={"cache_results": True},
    )

    # Submit with evidence count = 10 (confidence = 0.943 -> safe to auto-apply)
    res = engine.submit_candidate(cand, evidence_count=10)
    assert res.status == CandidateStatus.APPLIED
    assert engine.consolidator.active_config["cache_results"] is True

    # Submit sensitive config (verify_permissions_preflight -> fails safety -> Pending status)
    cand_sensitive = LearningCandidate(
        candidate_id="c_sens",
        target_type="ConstraintRule",
        explanation="Toggle auth checks preflight",
        proposed_update={"verify_permissions_preflight": True},
    )
    res_sens = engine.submit_candidate(cand_sensitive, evidence_count=15)
    assert res_sens.status == CandidateStatus.PENDING

    # Manually approve
    success = engine.approve_candidate("c_sens")
    assert success is True
    assert engine.queue["c_sens"].status == CandidateStatus.APPLIED
    assert engine.consolidator.active_config["verify_permissions_preflight"] is True
