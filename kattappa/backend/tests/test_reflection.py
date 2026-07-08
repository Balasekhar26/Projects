"""Unit and integration tests for Program 6: Reflection Engine.
"""
from __future__ import annotations

import pytest

from backend.core.reflection.models import ExecutionRecord, ExecutionReview, LearningCandidate
from backend.core.reflection.analyzer import FailureClassifier, OptimizationAnalyzer
from backend.core.reflection.recommendations import RecommendationGenerator
from backend.core.reflection.reflection_engine import ReflectionEngine


def test_failure_classification():
    """Verifies that FailureClassifier classifies error string details to target categories."""
    # 1. Network
    f_net = [{"error_message": "Network socket timeout connection error"}]
    assert FailureClassifier.classify(f_net) == "Network"

    # 2. Permission
    f_perm = [{"error_message": "Permission denied: unauthorized credentials token"}]
    assert FailureClassifier.classify(f_perm) == "Permission"

    # 3. None/No failure
    assert FailureClassifier.classify([]) is None


def test_optimization_analyzer_bottlenecks_and_parallel():
    """Verifies that OptimizationAnalyzer identifies slow tasks and parallel scores."""
    durations = {
        "node_1": 1.0,
        "node_2": 8.0,  # Fails threshold / bottleneck
        "node_3": 1.2,
    }
    bottlenecks = OptimizationAnalyzer.find_bottlenecks(durations, threshold=3.0)
    assert bottlenecks == ["node_2"]

    record = ExecutionRecord(
        session_id="s1",
        plan_id="p1",
        status="Completed",
        total_duration=10.2,
        task_durations=durations,
    )
    score = OptimizationAnalyzer.analyze_parallelization(record)
    # max duration (8.0) / total duration (10.2)
    assert score == pytest.approx(8.0 / 10.2)


def test_recommendation_candidates_generation():
    """Verifies RecommendationGenerator produces learning candidates based on performance metrics."""
    review = ExecutionReview(
        session_id="session_abc",
        success_rate=80.0,
        avg_latency=1.5,
        total_retries=1,
        failure_category="Network",
        bottleneck_nodes=["node_2"],
        parallelization_score=0.2,  # sequentially bound
    )

    candidates = RecommendationGenerator.generate(review)
    assert len(candidates) > 0

    # Verify that a RetryLimit candidate for Network is generated
    net_cand = next(c for c in candidates if c.target_type == "RetryLimit")
    assert "network-related failures" in net_cand.explanation
    assert net_cand.proposed_update["max_retries"] == 5

    # Verify that a ToolPolicy candidate for node_2 bottleneck is generated
    tool_cand = next(c for c in candidates if c.target_type == "ToolPolicy")
    assert tool_cand.proposed_update["target_node"] == "node_2"


def test_reflection_engine_end_to_end():
    """Integration test: submits finished ExecutionRecord, triggers reflection, and retrieves candidates."""
    engine = ReflectionEngine()

    durations = {"Step1": 1.0, "Step2": 1.5}
    failures = [{"error_message": "Rate limits exceeded on API query"}]
    retries = {"Step2": 2}

    record = ExecutionRecord(
        session_id="session_xyz",
        plan_id="plan_xyz",
        status="Failed",
        total_duration=5.0,
        task_durations=durations,
        retries=retries,
        failures=failures,
    )

    review = engine.process_execution(record)

    # Verifications
    assert review.session_id == "session_xyz"
    assert review.success_rate == pytest.approx(2.0 / 3.0 * 100.0)
    assert review.failure_category == "API"
    assert review.total_retries == 2

    # Retrieve learning candidates
    candidates = engine.get_candidates("session_xyz")
    assert len(candidates) > 0
    # Average latency is (1.0+1.5)/2 = 1.25. Threshold is 3.0, so no bottlenecks expected.
    assert len(review.bottleneck_nodes) == 0
