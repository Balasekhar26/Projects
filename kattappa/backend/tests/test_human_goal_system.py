import pytest
import tempfile
import shutil
import time
from pathlib import Path
from backend.core.goal_memory import GoalMemory
from backend.core.goal_manager import GoalManager, GoalStatus

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_human_goals_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    GoalMemory._schema_ensured = False
    GoalMemory.reset()

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_human_goal_schema_additions():
    # Retrieve connection and inspect schema columns
    conn = GoalMemory._get_sqlite_conn()
    try:
        cursor = conn.execute("PRAGMA table_info(goals)")
        columns = {row["name"] for row in cursor.fetchall()}
        
        # Verify Human-Like additions are present
        assert "parent_goal_id" in columns
        assert "provenance" in columns
        assert "original_goal_text" in columns
        assert "definition_of_done" in columns
        assert "ttl" in columns
        assert "decay_rate" in columns
        assert "estimated_value" in columns
        assert "confidence_score" in columns

        # Verify new tables
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "goal_values" in tables
        assert "goal_conflicts" in tables
        assert "goal_metrics" in tables
    finally:
        conn.close()


def test_goal_creation_and_provenance():
    # 1. Stated Goal Creation
    stated_goal = GoalManager.add_goal(
        title="Deploy Security Engine",
        provenance="STATED",
        importance_score=80.0,
        urgency_score=70.0,
        current_state="IDEA",
    )
    assert stated_goal["provenance"] == "STATED"
    assert stated_goal["current_state"] == "IDEA"

    # Start Stated Goal -> should be allowed
    active_stated = GoalManager.start(stated_goal["goal_id"])
    assert active_stated["status"] == "ACTIVE"

    # 2. Inferred Goal Creation
    inferred_goal = GoalManager.add_goal(
        title="Refactor Legacy Logger",
        provenance="INFERRED",
        current_state="IDEA",
    )
    assert inferred_goal["provenance"] == "INFERRED"

    # Attempt to start Inferred Goal -> should raise ValueError
    with pytest.raises(ValueError, match="Cannot execute INFERRED goal directly"):
        GoalManager.start(inferred_goal["goal_id"])

    # Approve/promote Inferred Goal
    approved = GoalMemory.update_goal_status(inferred_goal["goal_id"], "APPROVED")
    assert approved["provenance"] == "STATED"

    # Start after promotion -> should be allowed
    active_inferred = GoalManager.start(inferred_goal["goal_id"])
    assert active_inferred["status"] == "ACTIVE"


def test_priority_score_decay():
    # 1. Normal priority score
    goal = GoalManager.add_goal(
        title="Audit Token Budgets",
        importance_score=80.0,
        urgency_score=80.0,
        decay_rate=0.0
    )
    # default values: importance_score=80, urgency_score=80, alignment=50, value=50, confidence=1.0
    # denominator: energy=2.0, risk=10.0, decay=1.0 -> 20.0
    # expected: (80 * 80 * 50 * 50 * 1.0) / 20.0 = 800000.0
    g_id = goal["goal_id"]
    retrieved = GoalManager.get(g_id)
    assert retrieved["priority_score"] == 800000.0

    # 2. Priority score with decay over time
    decay_goal = GoalMemory.create_goal(
        title="Decaying Goal Idea",
        importance_score=80.0,
        urgency_score=80.0,
        decay_rate=0.5, # 50% decay per day
    )
    dg_id = decay_goal["goal_id"]
    
    # Check immediate score (decay elapsed days = 0.0) -> should be close to 800000.0
    assert decay_goal["priority_score"] == pytest.approx(800000.0, rel=1e-3)

    # Mock reviewed time to 2 days in the past (elapsed days = 2.0)
    # decay_coeff = e^(0.5 * 2) = e^1 = 2.71828
    # denominator: 20 * 2.71828 = 54.3656
    # expected score: 16000000 / 54.3656 = 294266.97
    past_reviewed = time.time() - (2 * 86400)
    conn = GoalMemory._get_sqlite_conn()
    try:
        conn.execute("UPDATE goals SET last_reviewed_at = ? WHERE goal_id = ?", (past_reviewed, dg_id))
        conn.commit()
    finally:
        conn.close()

    decayed = GoalManager.get(dg_id)
    assert decayed["priority_score"] < 300000.0
    assert decayed["priority_score"] > 290000.0


def test_goal_conflicts_and_resolution():
    goal_a = GoalManager.add_goal("Goal A")
    goal_b = GoalManager.add_goal("Goal B")
    
    # Declare conflict
    conflict = GoalMemory.add_conflict(
        goal_a_id=goal_a["goal_id"],
        goal_b_id=goal_b["goal_id"],
        conflict_topology="RESOURCE",
        severity_rating=85.0
    )
    assert conflict["conflict_id"].startswith("conflict_")
    
    # Assert status transitions to CONFLICTED
    assert GoalManager.get(goal_a["goal_id"])["status"] == "CONFLICTED"
    assert GoalManager.get(goal_b["goal_id"])["status"] == "CONFLICTED"

    # Resolve conflict
    GoalMemory.resolve_conflict(conflict["conflict_id"], "MITIGATED")
    
    # Verify restored status to ACTIVE
    assert GoalManager.get(goal_a["goal_id"])["status"] == "ACTIVE"
    assert GoalManager.get(goal_b["goal_id"])["status"] == "ACTIVE"


def test_goal_ttl_expiration_and_reaffirmation():
    # Create goal with 1 second TTL
    goal = GoalMemory.create_goal(
        title="Short lived goal",
        ttl=1.0, # 1 second TTL
        current_state="IDEA",
    )
    g_id = goal["goal_id"]
    assert goal["current_state"] == "IDEA"

    # Mock reaff time to 2 seconds ago
    past_reaff = time.time() - 2.0
    conn = GoalMemory._get_sqlite_conn()
    try:
        conn.execute("UPDATE goals SET last_reaffirmed_at = ? WHERE goal_id = ?", (past_reaff, g_id))
        conn.commit()
    finally:
        conn.close()

    # Querying the goal should check TTL and transition it to DORMANT
    dormant_goal = GoalManager.get(g_id)
    assert dormant_goal["current_state"] == "DORMANT"
    assert dormant_goal["priority_score"] == 0.0 # Dormant goals are not prioritized

    # Reaffirm the goal -> should restore state to ACTIVE and reset TTL timer
    reaffirmed = GoalManager.reaffirm(g_id)
    assert reaffirmed["current_state"] == "ACTIVE"
    assert reaffirmed["priority_score"] > 0.0
    assert reaffirmed["last_reaffirmed_at"] > time.time() - 1.0


def test_semantic_drift_monitoring():
    goal = GoalMemory.create_goal(
        title="Fix Login Session Leak",
        description="Verify and patch Redis token pool leak after disconnect.",
    )
    g_id = goal["goal_id"]

    # Initial check -> Jaccard distance = 0, drift_detected = False
    status = GoalMemory.check_goal_drift(g_id)
    assert status["drift_detected"] is False
    assert status["drift_score"] == 0.0

    # Modify title and description significantly
    conn = GoalMemory._get_sqlite_conn()
    try:
        conn.execute(
            "UPDATE goals SET title = 'Build Audio Synthesizer App', description = 'Implement midi keyboard controls in react dashboard' WHERE goal_id = ?",
            (g_id,)
        )
        conn.commit()
    finally:
        conn.close()

    # Verify drift monitor detects semantic drift
    status_drift = GoalMemory.check_goal_drift(g_id)
    assert status_drift["drift_detected"] is True
    assert status_drift["drift_score"] > 0.5
