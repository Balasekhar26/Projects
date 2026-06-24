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
    DecisionContext
)
from backend.core.identity_system import IdentitySystem
from backend.core.cognitive_dashboard import CognitiveDashboardManager


@pytest.fixture(autouse=True)
def clean_db():
    # Make sure we clean dashboard tables before and after each test
    def _do_clean():
        from backend.core.verification_engine import VerificationEngine
        from backend.core.cognitive_dashboard import CognitiveDashboardManager
        from backend.core.goal_memory import GoalMemory
        from backend.core.project_memory import ProjectMemory
        from backend.core.identity_system import IdentitySystem
        from backend.core.executive_planner import ExecutivePlanner
        VerificationEngine._schema_ensured = False
        CognitiveDashboardManager._schema_ensured = False
        GoalMemory._schema_ensured = False
        ProjectMemory._schema_ensured = False
        IdentitySystem._schema_ensured = False
        ExecutivePlanner._schema_ensured = False

        conn = CognitiveDashboardManager._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM dashboard_proposals")
            conn.execute("DELETE FROM health_events")
            conn.execute("DELETE FROM identity_monitor_log")
            conn.execute("DELETE FROM tool_telemetry")
            conn.execute("DELETE FROM benchmark_tracks")
            conn.execute("DELETE FROM agent_operations")
            conn.execute("DELETE FROM epistemic_research")
            conn.execute("DELETE FROM project_telemetry")
            conn.execute("DELETE FROM goal_telemetry")
            conn.execute("DELETE FROM dashboard_snapshots")
            
            # Clean LIS profiles
            conn.execute("DELETE FROM lis_identity_profile")
            now = time.time()
            conn.execute(
                "INSERT INTO lis_identity_profile (profile_id, current_health_state, composite_health_score, last_verification_timestamp) VALUES (?, ?, ?, ?)",
                ("default_profile", "EXEMPLARY", 100.0, now)
            )
            conn.commit()
        finally:
            conn.close()

    _do_clean()
    yield
    _do_clean()


def test_dashboard_tables_exist():
    conn = CognitiveDashboardManager._get_sqlite_conn()
    try:
        tables = [
            "dashboard_snapshots",
            "goal_telemetry",
            "project_telemetry",
            "epistemic_research",
            "agent_operations",
            "benchmark_tracks",
            "tool_telemetry",
            "identity_monitor_log",
            "health_events",
            "dashboard_proposals"
        ]
        for t in tables:
            cursor = conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{t}'")
            assert cursor.fetchone() is not None, f"Table {t} does not exist!"
    finally:
        conn.close()


def test_collect_and_retrieve_latest_snapshot():
    from backend.core.project_memory import ProjectMemory
    from backend.core.executive_planner import ExecutivePlanner
    print("DEBUG: ProjectMemory schema_ensured =", ProjectMemory._schema_ensured)
    print("DEBUG: ExecutivePlanner schema_ensured =", ExecutivePlanner._schema_ensured)
    # Perform a sweep
    snap = CognitiveDashboardManager.collect_snapshot()
    assert snap is not None
    assert "snapshot_id" in snap
    assert "global_system_state" in snap
    assert snap["composite_health_score"] >= 0.0
    
    # Retrieve
    retrieved = CognitiveDashboardManager.get_latest_snapshot()
    assert retrieved["snapshot_id"] == snap["snapshot_id"]
    assert retrieved["global_system_state"] == snap["global_system_state"]


def test_composite_health_states():
    conn = CognitiveDashboardManager._get_sqlite_conn()
    try:
        # Mock LIS score < 40 to trigger CRITICAL global state
        conn.execute("UPDATE lis_identity_profile SET composite_health_score = 35.0 WHERE profile_id = 'default_profile'")
        conn.commit()
        
        snap = CognitiveDashboardManager.collect_snapshot()
        assert snap["global_system_state"] == "CRITICAL"
        assert snap["composite_health_score"] < 40.0
        
        # Check that restricted mode is triggered
        assert CognitiveDashboardManager.is_restricted_mode() is True

        # Check that critical event is logged
        events = CognitiveDashboardManager.get_health_events()
        assert len(events) > 0
        assert events[0]["severity"] == "CRITICAL"

        # Mock health score 55 to trigger DEGRADED global state
        conn.execute("UPDATE lis_identity_profile SET composite_health_score = 55.0 WHERE profile_id = 'default_profile'")
        conn.commit()

        snap = CognitiveDashboardManager.collect_snapshot()
        assert snap["global_system_state"] == "DEGRADED"

        # Check that repair proposal is generated
        props = CognitiveDashboardManager.get_repair_proposals()
        assert len(props) > 0
        assert props[0]["status"] == "PENDING"
    finally:
        conn.close()


def test_restricted_mode_blocks_consensus():
    conn = CognitiveDashboardManager._get_sqlite_conn()
    try:
        # Mock LIS score to 35.0 (CRITICAL state / Restricted Mode)
        conn.execute("UPDATE lis_identity_profile SET composite_health_score = 35.0 WHERE profile_id = 'default_profile'")
        conn.commit()
        
        # Generate health snapshot to set latest health to CRITICAL
        CognitiveDashboardManager.collect_snapshot()
        
        # Assert restricted mode
        assert CognitiveDashboardManager.is_restricted_mode() is True

        # Mock standard votes
        outputs = [
            AgentOutput(
                agent="Engineer",
                decision=Decision.APPROVE,
                confidence=0.9,
                constraints=(),
                recommendations=(Recommendation(source="Engineer", message="build code", weight=1.0),),
                veto=None,
                evidence=(),
                critic_findings=(),
                source_id="engine_run",
                rationale="ready"
            )
        ]
        
        # ConsensusEngine decide must escalate decision to require human review and clear selected
        context = DecisionContext(project="test_proj")
        decision = ConsensusEngine.decide(outputs, context)
        assert decision.status == ConsensusStatus.ESCALATE
        assert decision.selected is None
        assert decision.requires_human_approval is True
        assert any("Restricted Mode active" in r for r in decision.reasons)
    finally:
        conn.close()


def test_approve_repair_proposal():
    conn = CognitiveDashboardManager._get_sqlite_conn()
    try:
        # Set degraded state and trigger proposal
        conn.execute("UPDATE lis_identity_profile SET composite_health_score = 55.0 WHERE profile_id = 'default_profile'")
        conn.commit()
        CognitiveDashboardManager.collect_snapshot()
        
        props = CognitiveDashboardManager.get_repair_proposals()
        assert len(props) > 0
        pending_prop = props[0]
        assert pending_prop["status"] == "PENDING"

        # Resolve via approval
        success = CognitiveDashboardManager.approve_repair_proposal(pending_prop["proposal_id"])
        assert success is True

        # Check LIS health is restored to 100
        profile = IdentitySystem.get_or_create_profile()
        assert profile["composite_health_score"] == 100.0
        assert profile["current_health_state"] == "EXEMPLARY"

        # Check health event resolving
        events = CognitiveDashboardManager.get_health_events()
        for evt in events:
            if evt["severity"] in ("CRITICAL", "WARNING"):
                assert evt["resolved_at"] is not None
    finally:
        conn.close()
