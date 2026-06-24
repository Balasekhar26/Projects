# test_identity_system.py
# ========================
# Integration and unit tests for the Long-Term Identity System (LIS).

from __future__ import annotations

import sqlite3
import time
import pytest

from backend.core.consensus_engine import (
    AgentOutput,
    ConsensusEngine,
    ConsensusStatus,
    Decision,
    Recommendation,
    Veto,
)
from backend.core.identity_system import IdentitySystem


@pytest.fixture(autouse=True)
def clean_db():
    # Make sure we clean/seed tables before and after each test
    def _do_clean():
        conn = IdentitySystem._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM lis_drift_tracker")
            conn.execute("DELETE FROM lis_role_logs")
            conn.execute("DELETE FROM lis_identity_ledger")
            conn.execute("DELETE FROM lis_value_checks")
            conn.execute("DELETE FROM lis_identity_metrics")
            conn.execute("DELETE FROM lis_identity_profile")
            
            # Seed default profile clean
            now = time.time()
            conn.execute(
                "INSERT INTO lis_identity_profile (profile_id, current_health_state, composite_health_score, last_verification_timestamp) VALUES (?, ?, ?, ?)",
                ("default_profile", "EXEMPLARY", 100.0, now)
            )
            conn.execute(
                "INSERT INTO lis_identity_metrics (profile_id, rolling_truth_index, rolling_alignment_index, rolling_reliability_index, rolling_learning_index, rolling_creativity_index, updated_at) VALUES (?, 100.0, 100.0, 100.0, 100.0, 100.0, ?)",
                ("default_profile", now)
            )
            conn.commit()
        finally:
            conn.close()

    _do_clean()
    yield
    _do_clean()


def test_get_or_create_profile():
    profile = IdentitySystem.get_or_create_profile("test_profile")
    assert profile["profile_id"] == "test_profile"
    assert profile["current_health_state"] == "EXEMPLARY"
    assert profile["composite_health_score"] == 100.0
    
    autonomy = IdentitySystem.get_autonomy_level("test_profile")
    assert autonomy == "FULL_AUTONOMY"


def test_derive_role_weights_boundaries():
    # Domain specific Teacher match
    weights = IdentitySystem.derive_role_weights({"domain": "explain concepts to user"})
    assert weights["Teacher"] >= 0.30  # Floor for matched domain
    assert weights["Teacher"] <= 0.60  # Ceiling
    assert abs(sum(weights.values()) - 1.0) < 1e-6

    # Domain specific Engineer match
    weights_eng = IdentitySystem.derive_role_weights({"domain": "architect database code"})
    assert weights_eng["Engineer"] >= 0.30
    assert weights_eng["Engineer"] <= 0.60
    assert abs(sum(weights_eng.values()) - 1.0) < 1e-6

    # Verifying floor bounds are respected for non-matched roles
    for role, val in weights_eng.items():
        if role != "Engineer":
            assert val >= 0.10


def test_truth_gate_evaluation():
    # Passed verification
    assert IdentitySystem.evaluate_truth_gate({"verification": {"outcome": "VERIFIED"}}) is True
    
    # Failed verification status
    assert IdentitySystem.evaluate_truth_gate({"verification": {"outcome": "FAILED"}}) is False
    assert IdentitySystem.evaluate_truth_gate({"verification": {"status": "CONTRADICTED"}}) is False
    
    # Low confidence score
    assert IdentitySystem.evaluate_truth_gate({"verification": {"score": 0.40}}) is False
    assert IdentitySystem.evaluate_truth_gate({"verification": {"confidence_score": 0.30}}) is False
    
    # Low truthfulness rating
    assert IdentitySystem.evaluate_truth_gate({"truthfulness_rating": 40}) is False
    assert IdentitySystem.evaluate_truth_gate({"truthfulness_rating": 80}) is True


def test_ledger_and_retraction():
    profile_id = "default_profile"
    action_id = "action_1"
    verification_report_id = "report_1"
    
    # Verify starting health
    profile = IdentitySystem.get_or_create_profile(profile_id)
    assert profile["composite_health_score"] == 100.0
    
    # Record bad behavior (TRUTH score drops by 60.0, composite health should drop accordingly)
    # TRUTH has 30% weight, so delta of -60 should lower composite health by 18 points (from 100 to 82)
    entry_id = IdentitySystem.record_behavior(
        profile_id=profile_id,
        action_id=action_id,
        verification_report_id=verification_report_id,
        evidence_hash="hash123",
        summary="Failed to verify factual claims",
        value="TRUTH",
        delta=-60.0
    )
    
    updated_profile = IdentitySystem.get_or_create_profile(profile_id)
    assert updated_profile["composite_health_score"] < 100.0
    assert updated_profile["composite_health_score"] == pytest.approx(82.0)
    assert updated_profile["current_health_state"] == "STRONG"  # 75-89 is STRONG

    # Retract the behavior
    retract_entry_id = IdentitySystem.retract_behavior(
        profile_id=profile_id,
        target_report_id=verification_report_id,
        retraction_reason="audit confirmed accuracy"
    )
    assert retract_entry_id is not None
    
    # Verify score recovered to original 100.0
    recovered_profile = IdentitySystem.get_or_create_profile(profile_id)
    assert recovered_profile["composite_health_score"] == pytest.approx(100.0)
    assert recovered_profile["current_health_state"] == "EXEMPLARY"


def test_drift_alarms():
    profile_id = "default_profile"
    
    # To trip sycophancy: TRUTH drops (delta < 0) and ALIGNMENT rises (delta > 0) in recent 10 logs
    # Let's add multiple logs to establish this trend.
    for i in range(5):
        IdentitySystem.record_behavior(profile_id, f"a_{i}", f"r_t_{i}", "h", "ch", "TRUTH", -10.0)
        IdentitySystem.record_behavior(profile_id, f"a_{i}", f"r_a_{i}", "h", "ch", "ALIGNMENT", 5.0)

    # Query drift tracker database to check if SYCOPHANCY_INDEX alarm tripped
    conn = IdentitySystem._get_sqlite_conn()
    try:
        tripped = conn.execute(
            "SELECT COUNT(*) as count FROM lis_drift_tracker WHERE profile_id = ? AND metric_monitored = 'SYCOPHANCY_INDEX' AND is_alarm_tripped = 1",
            (profile_id,)
        ).fetchone()
        assert tripped["count"] > 0
    finally:
        conn.close()


def test_autonomy_gating_integration():
    profile_id = "default_profile"
    
    # Record bad behaviors to drop health below 60.0 (Reduced Autonomy)
    # TRUTH delta = -100.0 (rolling_truth = 0)
    # ALIGNMENT delta = -60.0 (rolling_alignment = 40)
    # Composite: 0.30*0 + 0.25*40 + 0.20*100 + 0.15*100 + 0.10*100 = 55.0
    IdentitySystem.record_behavior(profile_id, "act_d1", "rep_d1", "hash", "desc", "TRUTH", -100.0)
    IdentitySystem.record_behavior(profile_id, "act_d2", "rep_d2", "hash", "desc", "ALIGNMENT", -60.0)
    
    autonomy = IdentitySystem.get_autonomy_level(profile_id)
    assert autonomy == "REDUCED_AUTONOMY"
    
    # Check consensus integration: Reduced Autonomy forces requires_human_approval = True
    outputs = [
        AgentOutput("Engineer", Decision.APPROVE, source_id="m1"),
    ]
    # Use a dummy project to trigger weight derivation + project check
    decision = ConsensusEngine.decide(outputs)
    assert decision.status is ConsensusStatus.APPROVED
    assert decision.requires_human_approval is True
    assert any("Reduced Autonomy active" in r for r in decision.reasons)

    # Record more bad behaviors to drop health below 40.0 (Restricted Mode)
    # RELIABILITY delta = -100.0 (rolling_reliability = 0)
    # Composite: 0.30*0 + 0.25*40 + 0.20*0 + 0.15*100 + 0.10*100 = 35.0
    IdentitySystem.record_behavior(profile_id, "act_d3", "rep_d3", "hash", "desc", "RELIABILITY", -100.0)
    
    autonomy_crit = IdentitySystem.get_autonomy_level(profile_id)
    assert autonomy_crit == "RESTRICTED_MODE"
    
    # Verify consensus decider forces Restricted Mode constraints
    crit_decision = ConsensusEngine.decide(outputs)
    assert crit_decision.requires_human_approval is True
    assert any("Restricted Mode active" in r for r in crit_decision.reasons)
