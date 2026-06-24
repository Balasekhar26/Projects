"""Tests for Council Validation & Benchmarking (Step 16)."""

from __future__ import annotations

import json
import time
import uuid
import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from backend.main import app

from backend.core.council_benchmark_validator import (
    VALIDATION_SUITE,
    ValidationCase,
    CouncilBenchmarkValidator,
    GroupScorecard,
    ComparisonReport,
)
from backend.core.council_session import CouncilSession
from backend.core.self_improvement_governance import SelfImprovementGovernance


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("KATTAPPA_DATA_DIR", str(tmp_path))
    from backend.core.council_session import _schema_ensured as cs_ensured
    from backend.core.self_improvement_governance import _schema_ensured as sig_ensured
    cs_ensured.clear()
    sig_ensured.clear()
    yield


# ── Suite Completeness ────────────────────────────────────────────────────────

def test_validation_suite_completeness():
    assert len(VALIDATION_SUITE) == 12
    categories = {case.question_type for case in VALIDATION_SUITE}
    assert "safety" in categories
    assert "architecture" in categories
    assert "research" in categories
    assert "user_impact" in categories
    assert "general" in categories


# ── Group A Runner Tests ──────────────────────────────────────────────────────

def test_group_a_runs_correctly():
    # Define a small mock suite of 3 cases
    mock_suite = [
        ValidationCase("c1", "Q1", "safety", "REJECT", "REJECT"),
        ValidationCase("c2", "Q2", "architecture", "APPROVE", "APPROVE"),
        ValidationCase("c3", "Q3", "user_impact", "REJECT", "REJECT"),
    ]

    mock_responses = [
        '{"decision": "REJECT", "confidence": 0.9, "rationale": "Unsafe"}',
        '{"decision": "APPROVE", "confidence": 0.8, "rationale": "Optimized Cache"}',
        '{"decision": "APPROVE", "confidence": 0.7, "rationale": "Telugu setting"}',
    ]
    response_idx = 0

    def fake_ask_model(prompt, role, system):
        nonlocal response_idx
        res = mock_responses[response_idx]
        response_idx += 1
        return res

    mock_gate_decision = MagicMock()
    mock_gate_decision.gate_status = "pending"
    mock_gate_decision.passed = True

    with patch("backend.core.council_benchmark_validator.ask_model", side_effect=fake_ask_model), \
         patch.object(SelfImprovementGovernance, "submit", return_value=mock_gate_decision):
        scorecard = CouncilBenchmarkValidator._run_group_a(mock_suite)

    assert scorecard.total_llm_calls == 3
    # Q1: expected REJECT, got REJECT. Human pref REJECT. Recommendation: REJECT. Correct!
    # Q2: expected APPROVE, got APPROVE. Gov passed. Human pref APPROVE. Recommendation: APPROVE. Correct!
    # Q3: expected APPROVE, got APPROVE. Gov passed. Human pref REJECT. Recommendation: APPROVE. Reversal! Incorrect!
    assert scorecard.accuracy == pytest.approx(2/3, abs=0.01)
    assert scorecard.reversal_rate == 0.5  # 1 reversal (Q3) / 2 approvals (Q2, Q3)
    assert scorecard.human_satisfaction == pytest.approx(2/3, abs=0.01)  # Q1, Q2 match human preference
    assert scorecard.safety_accuracy == 1.0  # Q1 is safety, expected REJECT, got REJECT


# ── Group B Runner Tests ──────────────────────────────────────────────────────

def test_group_b_runs_correctly():
    mock_suite = [
        ValidationCase("c1", "Q1", "safety", "REJECT", "REJECT"),
        ValidationCase("c2", "Q2", "architecture", "APPROVE", "APPROVE"),
    ]

    # Mock CouncilResult values
    from backend.core.council_session import CouncilResult
    mock_result_reject = CouncilResult(
        decision_id=str(uuid.uuid4()),
        question="Q1",
        question_type="safety",
        consensus_status="rejected",
        requires_human_approval=False,
        selected_recommendation=None,
        approve_mass=0.0,
        reject_mass=5.0,
        margin=None,
        votes=[],
        audit_findings=[],
        reasons=[],
        created_at=time.time(),
    )

    mock_result_approve = CouncilResult(
        decision_id=str(uuid.uuid4()),
        question="Q2",
        question_type="architecture",
        consensus_status="approved",
        requires_human_approval=True,
        selected_recommendation="Approve",
        approve_mass=4.5,
        reject_mass=1.0,
        margin=3.5,
        votes=[],
        audit_findings=[],
        reasons=[],
        created_at=time.time(),
        governance_proposal_id="proposal_xyz",
    )

    results = [mock_result_reject, mock_result_approve]
    idx = 0

    def fake_deliberate(question, question_type, context, **kwargs):
        nonlocal idx
        res = results[idx]
        idx += 1
        return res

    with patch.object(CouncilSession, "deliberate", side_effect=fake_deliberate):
        scorecard = CouncilBenchmarkValidator._run_group_b(mock_suite, quick=False)

    assert scorecard.total_llm_calls == 24  # 12 calls per deliberate session
    # Q1: final recommendation REJECT, expected REJECT, human REJECT -> correct, match human
    # Q2: final recommendation APPROVE (since approved & governance pending/proposal ID present), expected APPROVE, human APPROVE -> correct, match human
    assert scorecard.accuracy == 1.0
    assert scorecard.reversal_rate == 0.0
    assert scorecard.human_satisfaction == 1.0
    assert scorecard.safety_accuracy == 1.0


# ── Success Criteria Evaluator Tests ──────────────────────────────────────────

def test_success_criteria_passed():
    # Case 1: Criteria met
    scorecard_a = GroupScorecard(
        accuracy=0.6,
        safety_accuracy=0.8,
        reversal_rate=0.4,
        human_satisfaction=0.6,
        avg_latency_ms=100.0,
        total_llm_calls=3,
        total_estimated_tokens=500,
        decisions=[],
    )
    scorecard_b = GroupScorecard(
        accuracy=0.72,            # 12% improvement (>= 10% met)
        safety_accuracy=0.86,     # 6% improvement (>= 5% met)
        reversal_rate=0.2,        # decreased met
        human_satisfaction=0.75,  # increased met
        avg_latency_ms=1200.0,
        total_llm_calls=36,
        total_estimated_tokens=6000,
        decisions=[],
    )

    with patch.object(CouncilBenchmarkValidator, "_run_group_a", return_value=scorecard_a), \
         patch.object(CouncilBenchmarkValidator, "_run_group_b", return_value=scorecard_b):
        report = CouncilBenchmarkValidator.run_comparative_benchmark(VALIDATION_SUITE)

    assert report.success_criteria_passed is True

    # Case 2: Criteria not met (accuracy improvement too small)
    scorecard_b_low_acc = GroupScorecard(
        accuracy=0.65,            # only 5% improvement (< 10% limit)
        safety_accuracy=0.86,
        reversal_rate=0.2,
        human_satisfaction=0.75,
        avg_latency_ms=1200.0,
        total_llm_calls=36,
        total_estimated_tokens=6000,
        decisions=[],
    )

    with patch.object(CouncilBenchmarkValidator, "_run_group_a", return_value=scorecard_a), \
         patch.object(CouncilBenchmarkValidator, "_run_group_b", return_value=scorecard_b_low_acc):
        report_fail = CouncilBenchmarkValidator.run_comparative_benchmark(VALIDATION_SUITE)

    assert report_fail.success_criteria_passed is False


# ── REST API Route Tests ──────────────────────────────────────────────────────

def test_api_endpoint_success():
    client = TestClient(app)

    # Mock scorecards
    sc_a = GroupScorecard(
        accuracy=0.7, safety_accuracy=0.9, reversal_rate=0.1, human_satisfaction=0.8,
        avg_latency_ms=150.0, total_llm_calls=12, total_estimated_tokens=1000, decisions=[]
    )
    sc_b = GroupScorecard(
        accuracy=0.85, safety_accuracy=0.95, reversal_rate=0.05, human_satisfaction=0.9,
        avg_latency_ms=800.0, total_llm_calls=48, total_estimated_tokens=4000, decisions=[]
    )

    report = ComparisonReport(
        group_a=sc_a,
        group_b=sc_b,
        success_criteria_passed=True,
        reasons=["All metrics met"]
    )

    with patch.object(CouncilBenchmarkValidator, "run_comparative_benchmark", return_value=report):
        payload = {"quick_council": True, "quick_n": 3}
        response = client.post("/council/benchmark/validate", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success_criteria_passed"] is True
    assert data["group_a"]["accuracy"] == 0.7
    assert data["group_b"]["accuracy"] == 0.85
