from __future__ import annotations

import json
import sqlite3
import time
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.core.project_memory import ProjectMemory
from backend.core.continuous_benchmark import ContinuousBenchmarkRunner, BASELINE_SEED
from backend.core.cognitive_dashboard import CognitiveDashboardManager


@pytest.fixture(autouse=True)
def clean_db():
    """Make sure we clean project memory and benchmark tables before and after each test."""
    def _do_clean():
        from backend.core.verification_engine import VerificationEngine
        from backend.core.cognitive_dashboard import CognitiveDashboardManager
        from backend.core.goal_memory import GoalMemory
        from backend.core.project_memory import ProjectMemory
        from backend.core.identity_system import IdentitySystem
        from backend.core.executive_planner import ExecutivePlanner
        from backend.core.resource_governor import ResourceGovernor

        VerificationEngine._schema_ensured = False
        CognitiveDashboardManager._schema_ensured = False
        GoalMemory._schema_ensured = False
        ProjectMemory._schema_ensured = False
        IdentitySystem._schema_ensured = False
        ExecutivePlanner._schema_ensured = False

        ResourceGovernor.reset()

        conn = CognitiveDashboardManager._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM continuous_benchmarks")
            conn.execute("DELETE FROM dashboard_snapshots")
            conn.execute("DELETE FROM benchmark_tracks")
            conn.commit()
        finally:
            conn.close()

    _do_clean()
    yield
    _do_clean()


@pytest.fixture(autouse=True)
def bypass_resource_governor():
    with patch("backend.core.resource_governor.ResourceGovernor.check_token_budget", return_value=True):
        yield


def mock_ask_model(prompt: str, role: str = "general", system: str | None = None) -> str:
    """Mocks local LLM completions for benchmarks."""
    lower_prompt = prompt.lower()
    if "correctness and quality of kattappa" in lower_prompt:
        return json.dumps({
            "context_retention": 92.0,
            "identity_consistency": 94.0,
            "goal_awareness": 90.0,
            "preference_recall": 92.0
        })
    elif "planning output from the executive planner" in lower_prompt:
        return json.dumps({
            "planner_quality": 88.0,
            "verification_accuracy": 89.0,
            "scheduler_decisions": 87.0,
            "goal_prioritization": 88.0
        })
    elif "recommend 2 to 3" in lower_prompt:
        return json.dumps([
            "Mock Optimization Proposal 1",
            "Mock Optimization Proposal 2"
        ])
    return "Mock general model completion"


def mock_run_performance_suite():
    return {
        "planning_latency_ms": 100.0,
        "goal_creation_latency_ms": 20.0,
        "dashboard_query_latency_ms": 30.0,
        "scheduler_dispatch_latency_ms": 15.0,
        "verification_latency_ms": 25.0
    }


def mock_run_memory_suite():
    return {
        "sqlite_size_bytes": 100000.0,
        "ram_usage_bytes": 120000000.0,
        "goal_retrieval_latency_ms": 10.0,
        "project_retrieval_latency_ms": 10.0
    }


@patch("backend.core.continuous_benchmark.ask_model", side_effect=mock_ask_model)
@patch("backend.core.continuous_benchmark.ContinuousBenchmarkRunner._run_performance_suite", side_effect=mock_run_performance_suite)
@patch("backend.core.continuous_benchmark.ContinuousBenchmarkRunner._run_memory_suite", side_effect=mock_run_memory_suite)
def test_continuous_metrics_collection(mock_mem, mock_perf, mock_ll):
    """Verifies that running the continuous benchmark suite collects metrics successfully."""
    report = ContinuousBenchmarkRunner.run_suite()

    assert report is not None
    assert "run_id" in report
    assert report["regression_status"] == "PASS"  # Compared to seeded baseline, should pass
    assert len(report["proposals"]) == 2
    assert report["proposals"][0] == "Mock Optimization Proposal 1"

    # Verify metrics structure
    assert "planning_latency_ms" in report["performance_metrics"]
    assert "sqlite_size_bytes" in report["memory_metrics"]
    assert "context_retention" in report["conversation_metrics"]
    assert "planner_quality" in report["agent_metrics"]


@patch("backend.core.continuous_benchmark.ask_model", side_effect=mock_ask_model)
def test_regression_detection(mock_llm):
    """Verifies that regressions are detected and logged if current values swell by >15%."""
    baseline = {
        "performance": {
            "planning_latency_ms": 100.0,
            "goal_creation_latency_ms": 20.0,
            "dashboard_query_latency_ms": 30.0,
            "scheduler_dispatch_latency_ms": 10.0,
            "verification_latency_ms": 10.0,
        },
        "memory": {
            "sqlite_size_bytes": 100_000.0,
            "ram_usage_bytes": 100_000.0,
            "goal_retrieval_latency_ms": 10.0,
            "project_retrieval_latency_ms": 10.0,
        },
        "conversation": {
            "context_retention": 90.0,
            "identity_consistency": 90.0,
            "goal_awareness": 90.0,
            "preference_recall": 90.0,
        },
        "agent": {
            "planner_quality": 90.0,
            "verification_accuracy": 90.0,
            "scheduler_decisions": 90.0,
            "goal_prioritization": 90.0,
        }
    }

    # Case 1: No regression (equal to baseline)
    current_ok = {
        "performance": dict(baseline["performance"]),
        "memory": dict(baseline["memory"]),
        "conversation": dict(baseline["conversation"]),
        "agent": dict(baseline["agent"])
    }
    status, reasons = ContinuousBenchmarkRunner.detect_regressions(current_ok, baseline)
    assert status == "PASS"
    assert len(reasons) == 0

    # Case 2: Planning latency regression (+30% swell)
    current_slow = {
        "performance": {
            "planning_latency_ms": 130.0,  # +30% swell
            "goal_creation_latency_ms": 20.0,
            "dashboard_query_latency_ms": 30.0,
            "scheduler_dispatch_latency_ms": 10.0,
            "verification_latency_ms": 10.0,
        },
        "memory": dict(baseline["memory"]),
        "conversation": dict(baseline["conversation"]),
        "agent": dict(baseline["agent"])
    }
    status, reasons = ContinuousBenchmarkRunner.detect_regressions(current_slow, baseline)
    assert status == "REGRESSION"
    assert len(reasons) == 1
    assert "planning_latency_ms regression" in reasons[0]

    # Case 3: Memory footprint regression (+40% RAM usage swell)
    current_bloat = {
        "performance": dict(baseline["performance"]),
        "memory": {
            "sqlite_size_bytes": 100_000.0,
            "ram_usage_bytes": 140_000.0,  # +40% RAM swell
            "goal_retrieval_latency_ms": 10.0,
            "project_retrieval_latency_ms": 10.0,
        },
        "conversation": dict(baseline["conversation"]),
        "agent": dict(baseline["agent"])
    }
    status, reasons = ContinuousBenchmarkRunner.detect_regressions(current_bloat, baseline)
    assert status == "REGRESSION"
    assert len(reasons) == 1
    assert "ram_usage_bytes regression" in reasons[0]


@patch("backend.core.continuous_benchmark.ask_model", side_effect=mock_ask_model)
@patch("backend.core.continuous_benchmark.ContinuousBenchmarkRunner._run_performance_suite", side_effect=mock_run_performance_suite)
@patch("backend.core.continuous_benchmark.ContinuousBenchmarkRunner._run_memory_suite", side_effect=mock_run_memory_suite)
def test_dashboard_and_api_integration(mock_mem, mock_perf, mock_ll):
    """Verifies API endpoints and that dashboard snapshots capture continuous benchmark runs in Tier 6."""
    client = TestClient(app)

    # 1. Test POST run
    resp_run = client.post("/api/benchmark/continuous/run")
    assert resp_run.status_code == 200
    data_run = resp_run.json()
    assert "run_id" in data_run
    assert data_run["regression_status"] == "PASS"

    # 2. Test GET latest
    resp_latest = client.get("/api/benchmark/continuous/latest")
    assert resp_latest.status_code == 200
    data_latest = resp_latest.json()
    assert data_latest["run_id"] == data_run["run_id"]

    # 3. Test GET history
    resp_hist = client.get("/api/benchmark/continuous/history")
    assert resp_hist.status_code == 200
    data_hist = resp_hist.json()
    assert len(data_hist["history"]) >= 1

    # 4. Trigger cognitive dashboard snapshot sweep
    snap = CognitiveDashboardManager.collect_snapshot()
    assert snap is not None
    assert "tier_6_benchmarks" in snap
    
    # Assert custom metrics mapped successfully to vectors in Tier 6
    tracks = {t["capability_vector"]: t for t in snap["tier_6_benchmarks"]}
    assert "CONVERSATION" in tracks
    assert "PLANNING" in tracks
    assert "VERIFICATION" in tracks
    
    # Mapped from mock values: CONVERSATION average is int((92+94+90+92)/4) = 92
    assert tracks["CONVERSATION"]["score_value"] == 92
    assert tracks["PLANNING"]["score_value"] == 88
    assert tracks["VERIFICATION"]["score_value"] == 89
