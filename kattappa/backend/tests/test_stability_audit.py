from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from backend.core.config import load_config
from backend.core.goal_memory import GoalMemory
from backend.core.project_memory import ProjectMemory
from backend.core.identity_system import IdentitySystem
from backend.core.action_scheduler import ActionScheduler
from backend.core.cognitive_dashboard import CognitiveDashboardManager
from backend.core.continuous_benchmark import ContinuousBenchmarkRunner
from backend.core.verification_engine import VerificationEngine


@pytest.fixture(autouse=True)
def clean_db():
    """Ensures a clean database state before and after each stability test."""
    def _do_clean():
        # Clear schema ensuring flags to force re-initialization
        VerificationEngine._schema_ensured = False
        CognitiveDashboardManager._schema_ensured = False
        GoalMemory._schema_ensured = False
        ProjectMemory._schema_ensured = False
        IdentitySystem._schema_ensured = False
        ActionScheduler._schema_ensured = False

        from backend.core.resource_governor import ResourceGovernor
        ResourceGovernor.reset()

        conn = CognitiveDashboardManager._get_sqlite_conn()
        ActionScheduler._ensure_schema(conn)
        VerificationEngine._ensure_schema(conn)
        try:
            conn.execute("DELETE FROM continuous_benchmarks")
            conn.execute("DELETE FROM dashboard_snapshots")
            conn.execute("DELETE FROM benchmark_tracks")
            conn.execute("DELETE FROM goals")
            conn.execute("DELETE FROM projects")
            conn.execute("DELETE FROM tasks")
            conn.execute("DELETE FROM action_queue")
            conn.execute("DELETE FROM scheduler_metrics")
            conn.execute("DELETE FROM verification_reports")
            conn.execute("DELETE FROM lis_identity_profile")
            
            # Setup default profile
            now = time.time()
            conn.execute(
                "INSERT INTO lis_identity_profile (profile_id, current_health_state, composite_health_score, last_verification_timestamp) VALUES (?, ?, ?, ?)",
                ("default_profile", "EXEMPLARY", 100.0, now)
            )
            conn.commit()
        finally:
            conn.close()

        # Clean ActionScheduler's own database
        s_conn = ActionScheduler._get_conn()
        try:
            s_conn.execute("DELETE FROM action_queue")
            s_conn.execute("DELETE FROM scheduler_metrics")
            s_conn.commit()
        finally:
            s_conn.close()

    _do_clean()
    yield
    _do_clean()


@pytest.fixture(autouse=True)
def bypass_resource_governor():
    """Allows LLM actions to proceed without token budget blocks during stability tests."""
    with patch("backend.core.resource_governor.ResourceGovernor.check_token_budget", return_value=True):
        yield


def mock_ask_model(prompt: str, role: str = "general", system: str | None = None) -> str:
    """Simulated local model evaluator returning standard stable metrics."""
    lower_prompt = prompt.lower()
    if "correctness and quality of kattappa" in lower_prompt:
        return json.dumps({
            "context_retention": 95.0,
            "identity_consistency": 95.0,
            "goal_awareness": 95.0,
            "preference_recall": 95.0
        })
    elif "planning output from the executive planner" in lower_prompt:
        return json.dumps({
            "planner_quality": 95.0,
            "verification_accuracy": 95.0,
            "scheduler_decisions": 95.0,
            "goal_prioritization": 95.0
        })
    elif "recommend 2 to 3" in lower_prompt:
        return json.dumps([
            "Mock Proposal 1",
            "Mock Proposal 2"
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


# --- Test 1: Accelerated 24-Hour Autonomous Simulation ---
@patch("backend.core.continuous_benchmark.ask_model", side_effect=mock_ask_model)
@patch("backend.core.continuous_benchmark.ContinuousBenchmarkRunner._run_performance_suite", side_effect=mock_run_performance_suite)
@patch("backend.core.continuous_benchmark.ContinuousBenchmarkRunner._run_memory_suite", side_effect=mock_run_memory_suite)
def test_autonomous_simulation_loop(mock_mem, mock_perf, mock_ll):
    """Simulates 24 hours of autonomous activity via accelerated loop cycles."""
    start_time = time.time()
    
    # Run 24 fast iterations simulating hourly snapshots & scheduler checks
    for hour in range(24):
        # 1. Enqueue mock action
        ActionScheduler.enqueue_action(
            agent_name="RESEARCHER",
            action="web_search",
            params={"query": f"stability sweep hour {hour}"},
            state={},
            priority=5,
            deadline_secs=600.0,
            resource_estimate_pct=10.0
        )
        
        # 2. Run scheduler dispatch
        dispatched = ActionScheduler.dispatch_next()
        assert dispatched is not None
        
        # 3. Trigger periodic continuous benchmark
        if hour % 6 == 0:  # Every 6 simulated hours
            ContinuousBenchmarkRunner.run_suite()

        # 4. Trigger periodic dashboard snapshot
        if hour % 4 == 0:  # Every 4 simulated hours
            CognitiveDashboardManager.collect_snapshot()

    # Assert 24 actions were enqueued & managed correctly
    conn = ActionScheduler._get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM action_queue").fetchone()[0]
        assert count == 24
    finally:
        conn.close()
    
    # Assert dashboard snapshots are populated
    conn = CognitiveDashboardManager._get_sqlite_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM dashboard_snapshots").fetchone()[0]
        assert count > 0
    finally:
        conn.close()


# --- Test 2: Goal Persistence Test ---
def test_goal_persistence_recovery():
    """Verifies goal structure is intact and preserved across database sessions."""
    parent_id = "goal_parent"
    child_id = "goal_child"
    
    GoalMemory.create_goal(
        title="Stability Parent Goal",
        description="Verify parent persistency",
        goal_id=parent_id,
        parent_goal_id=None
    )
    
    GoalMemory.create_goal(
        title="Stability Child Goal",
        description="Verify parent-child association",
        goal_id=child_id,
        parent_goal_id=parent_id
    )

    # Force reset system schema flags and get new connection to simulate system restart
    GoalMemory._schema_ensured = False
    
    goals = GoalMemory.list_goals()
    goals_map = {g["goal_id"]: g for g in goals}
    
    assert parent_id in goals_map
    assert child_id in goals_map
    assert goals_map[child_id]["parent_goal_id"] == parent_id


# --- Test 3: Project Persistence Test ---
def test_project_persistence_recovery():
    """Verifies that projects, milestones, and tasks are correctly recovered after restart."""
    project_id = "proj_stability"
    
    GoalMemory.create_goal(
        title="Goal for Project Stability",
        goal_id="goal_stability_proj"
    )
    
    ProjectMemory.create_project(
        name="Stability Project",
        description="Audit project persistence",
        project_id=project_id
    )
    
    conn = ProjectMemory._get_sqlite_conn()
    try:
        conn.execute(
            "INSERT INTO milestones (milestone_id, goal_id, project_id, title, status, weight, progress, created_at, deadline) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("m_stab_1", "goal_stability_proj", project_id, "Milestone 1", "PENDING", 1.0, 0.0, time.time(), time.time() + 86400)
        )
        conn.commit()
    finally:
        conn.close()
        
    ProjectMemory.create_task(
        task_id="t_stab_1",
        milestone_id="m_stab_1",
        title="Stability Task",
        description="Audit task persistence"
    )

    # Simulate restart
    ProjectMemory._schema_ensured = False
    
    # Verify via project retrieval
    proj = ProjectMemory.get_project(project_id)
    assert proj is not None
    assert proj["project_id"] == project_id
    assert proj["name"] == "Stability Project"
    
    # Verify milestones and tasks exist in database
    conn = ProjectMemory._get_sqlite_conn()
    try:
        p_row = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        assert p_row is not None
        assert p_row["name"] == "Stability Project"
        
        m_row = conn.execute("SELECT * FROM milestones WHERE project_id = ?", (project_id,)).fetchone()
        assert m_row is not None
        assert m_row["milestone_id"] == "m_stab_1"
        
        t_row = conn.execute("SELECT * FROM tasks WHERE milestone_id = ?", ("m_stab_1",)).fetchone()
        assert t_row is not None
        assert t_row["task_id"] == "t_stab_1"
    finally:
        conn.close()


# --- Test 4: Memory Recovery after Restart ---
def test_memory_recovery():
    """Asserts that Identity profiles are preserved across database connection lifecycles."""
    profile_id = "audit_profile_unique"
    
    conn = IdentitySystem._get_sqlite_conn()
    try:
        conn.execute(
            "INSERT INTO lis_identity_profile (profile_id, current_health_state, composite_health_score, last_verification_timestamp) "
            "VALUES (?, 'STRONG', 85.0, ?)",
            (profile_id, time.time())
        )
        conn.commit()
    finally:
        conn.close()

    # Simulate restart
    IdentitySystem._schema_ensured = False
    
    profile = IdentitySystem.get_or_create_profile(profile_id)
    assert profile is not None
    assert profile["profile_id"] == profile_id
    assert profile["current_health_state"] == "STRONG"
    assert profile["composite_health_score"] == 85.0


# --- Test 5: Scheduler Recovery after Crash ---
def test_scheduler_crash_recovery():
    """Simulates a crash with in-flight actions and verifies resource reservations are reconstructed on startup."""
    # 1. Enqueue task requesting CPU reservation
    res = ActionScheduler.enqueue_action(
        agent_name="ENGINEER",
        action="deploy_service",
        params={},
        state={},
        priority=7,
        deadline_secs=600.0,
        resource_estimate_pct=45.0,
        ram_estimate_mb=128.0
    )
    
    # 2. Simulate task being IN_FLIGHT directly in DB to test recovery after a crash
    queue_id = res["queue_id"]
    conn = ActionScheduler._get_conn()
    try:
        conn.execute("UPDATE action_queue SET status = 'IN_FLIGHT' WHERE queue_id = ?", (queue_id,))
        conn.commit()
    finally:
        conn.close()
    
    # 3. Simulate sudden crash (forget schema cache and close scheduler reference)
    ActionScheduler._schema_ensured = False
    
    # 4. Get a fresh connection which runs _ensure_schema and scans IN_FLIGHT tasks
    conn = ActionScheduler._get_conn()
    try:
        # Verify that _ensure_schema ran during _get_conn(), which triggered scan and reconstruction.
        from backend.core.resource_governor import ResourceGovernor
        status = ResourceGovernor.get_status()
        
        # Verify allocations were successfully reconstructed in the governor
        assert status["reserved_cpu_percent"] == 45.0
        assert status["reserved_ram_mb"] == 128.0
    finally:
        conn.close()


# --- Test 6: Dashboard Recovery after Restart ---
def test_dashboard_recovery_after_restart():
    """Verifies that historical dashboard snapshots are persistent and recovered."""
    # Collect 3 snapshots
    for _ in range(3):
        CognitiveDashboardManager.collect_snapshot()
        time.sleep(0.01)

    # Simulate system restart
    CognitiveDashboardManager._schema_ensured = False
    
    latest = CognitiveDashboardManager.get_latest_snapshot()
    assert latest is not None
    assert "snapshot_id" in latest
    
    # Query database and verify all 3 snapshots exist
    conn = CognitiveDashboardManager._get_sqlite_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM dashboard_snapshots").fetchone()[0]
        assert count >= 3
    finally:
        conn.close()


# --- Test 7: Benchmark History Persistence ---
@patch("backend.core.continuous_benchmark.ask_model", side_effect=mock_ask_model)
@patch("backend.core.continuous_benchmark.ContinuousBenchmarkRunner._run_performance_suite", side_effect=mock_run_performance_suite)
@patch("backend.core.continuous_benchmark.ContinuousBenchmarkRunner._run_memory_suite", side_effect=mock_run_memory_suite)
def test_benchmark_history_persistence(mock_mem, mock_perf, mock_ll):
    """Verifies benchmark suite runs and optimization proposal history survive restarts."""
    # Execute benchmark suite
    ContinuousBenchmarkRunner.run_suite()

    # Restart benchmark runner context
    ProjectMemory._schema_ensured = False
    
    latest_report = ContinuousBenchmarkRunner.get_latest_report()
    assert latest_report is not None
    assert latest_report["regression_status"] == "PASS"
    assert len(latest_report["proposals"]) == 2
    
    history = ContinuousBenchmarkRunner.get_report_history()
    assert len(history) >= 1


# --- Test 8: Verification Ledger Persistence ---
def test_verification_ledger_persistence():
    """Asserts that logged verdicts in the Verification Engine ledger survive restarts."""
    queue_id = "q_verification_stability"
    
    # Log a verdict
    VerificationEngine.verify_result(
        queue_id=queue_id,
        action="read_file",
        agent_name="VERIFIER",
        params={"path": "audit_log.txt"},
        result={"success": True, "content": "mock audit log content", "checksum": "abc"}
    )

    # Simulate system restart
    VerificationEngine._schema_ensured = False
    
    reports = VerificationEngine.get_reports_for_action(queue_id)
    assert len(reports) == 1
    assert reports[0]["verdict"] == "VERIFIED"
    assert reports[0]["structural_pass"] == 1
    
    summary = VerificationEngine.get_verdicts_summary()
    assert summary["VERIFIED"] >= 1
