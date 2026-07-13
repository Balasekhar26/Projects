"""
Milestone 31: Goal Lifecycle Governor — Verification Suite.
Covers: state machine transitions, retry logic, subgoal advancement,
        priority scheduling, persistence (SQLite + Memory stores), and API endpoints.
"""
import time
import pytest
from backend.core.ledger.stores.sqlite_store import SQLiteLedgerStore
from backend.core.ledger.stores.memory_store import MemoryLedgerStore
from backend.core.governance.goal_lifecycle import (
    GoalLifecycleGovernor,
    GoalStatus,
    GoalTransitionError,
    can_transition,
    validate_transition,
)
from backend.core.governance.goal_scheduler import GoalPriorityScheduler


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(params=["sqlite", "memory"])
def store(request):
    if request.param == "sqlite":
        return SQLiteLedgerStore(db_path=":memory:")
    return MemoryLedgerStore()


@pytest.fixture
def governor(store):
    return GoalLifecycleGovernor(store)


@pytest.fixture
def scheduler():
    return GoalPriorityScheduler()


# ─────────────────────────────────────────────────────────────────────────────
# 1. State Machine: Valid Transitions
# ─────────────────────────────────────────────────────────────────────────────

class TestStateMachineValidTransitions:
    def test_created_to_planning(self, governor):
        goal = governor.create_goal("Deploy simulator")
        updated = governor.transition(goal["goal_id"], GoalStatus.PLANNING)
        assert updated["status"] == "PLANNING"

    def test_created_to_ready(self, governor):
        goal = governor.create_goal("Quick task")
        updated = governor.transition(goal["goal_id"], GoalStatus.READY)
        assert updated["status"] == "READY"

    def test_planning_to_ready(self, governor):
        goal = governor.create_goal("Plan something")
        governor.transition(goal["goal_id"], GoalStatus.PLANNING)
        updated = governor.transition(goal["goal_id"], GoalStatus.READY)
        assert updated["status"] == "READY"

    def test_ready_to_running(self, governor):
        goal = governor.create_goal("Run task")
        governor.transition(goal["goal_id"], GoalStatus.READY)
        updated = governor.transition(goal["goal_id"], GoalStatus.RUNNING)
        assert updated["status"] == "RUNNING"

    def test_running_to_completed(self, governor):
        goal = governor.create_goal("Finish task")
        for s in [GoalStatus.READY, GoalStatus.RUNNING]:
            governor.transition(goal["goal_id"], s)
        updated = governor.transition(goal["goal_id"], GoalStatus.COMPLETED)
        assert updated["status"] == "COMPLETED"

    def test_running_to_blocked(self, governor):
        goal = governor.create_goal("Blocked task")
        for s in [GoalStatus.READY, GoalStatus.RUNNING]:
            governor.transition(goal["goal_id"], s)
        updated = governor.transition(goal["goal_id"], GoalStatus.BLOCKED)
        assert updated["status"] == "BLOCKED"

    def test_running_to_failed(self, governor):
        goal = governor.create_goal("Failing task")
        for s in [GoalStatus.READY, GoalStatus.RUNNING]:
            governor.transition(goal["goal_id"], s)
        updated = governor.transition(goal["goal_id"], GoalStatus.FAILED)
        assert updated["status"] == "FAILED"

    def test_blocked_to_ready(self, governor):
        goal = governor.create_goal("Unblocked task")
        for s in [GoalStatus.READY, GoalStatus.RUNNING, GoalStatus.BLOCKED]:
            governor.transition(goal["goal_id"], s)
        updated = governor.transition(goal["goal_id"], GoalStatus.READY)
        assert updated["status"] == "READY"

    def test_completed_to_archived(self, governor):
        goal = governor.create_goal("Archive this")
        for s in [GoalStatus.READY, GoalStatus.RUNNING, GoalStatus.COMPLETED]:
            governor.transition(goal["goal_id"], s)
        updated = governor.transition(goal["goal_id"], GoalStatus.ARCHIVED)
        assert updated["status"] == "ARCHIVED"

    def test_failed_to_archived(self, governor):
        goal = governor.create_goal("Dead goal")
        for s in [GoalStatus.READY, GoalStatus.RUNNING, GoalStatus.FAILED]:
            governor.transition(goal["goal_id"], s)
        updated = governor.transition(goal["goal_id"], GoalStatus.ARCHIVED)
        assert updated["status"] == "ARCHIVED"


# ─────────────────────────────────────────────────────────────────────────────
# 2. State Machine: Invalid Transitions
# ─────────────────────────────────────────────────────────────────────────────

class TestStateMachineInvalidTransitions:
    @pytest.mark.parametrize("invalid_target", [
        GoalStatus.RUNNING,
        GoalStatus.COMPLETED,
        GoalStatus.BLOCKED,
    ])
    def test_created_cannot_jump_to(self, governor, invalid_target):
        goal = governor.create_goal("Test")
        with pytest.raises(GoalTransitionError):
            governor.transition(goal["goal_id"], invalid_target)

    def test_archived_is_terminal(self, governor):
        goal = governor.create_goal("Archive me")
        for s in [GoalStatus.READY, GoalStatus.RUNNING, GoalStatus.COMPLETED, GoalStatus.ARCHIVED]:
            governor.transition(goal["goal_id"], s)
        with pytest.raises(GoalTransitionError):
            governor.transition(goal["goal_id"], GoalStatus.CREATED)

    def test_running_cannot_go_to_created(self, governor):
        goal = governor.create_goal("No reset")
        for s in [GoalStatus.READY, GoalStatus.RUNNING]:
            governor.transition(goal["goal_id"], s)
        with pytest.raises(GoalTransitionError):
            governor.transition(goal["goal_id"], GoalStatus.CREATED)

    def test_missing_goal_raises_key_error(self, governor):
        with pytest.raises(KeyError):
            governor.transition("GOAL-NONEXISTENT", GoalStatus.READY)

    def test_can_transition_predicate_accurate(self):
        assert can_transition(GoalStatus.CREATED, GoalStatus.PLANNING) is True
        assert can_transition(GoalStatus.ARCHIVED, GoalStatus.CREATED) is False
        assert can_transition(GoalStatus.RUNNING, GoalStatus.COMPLETED) is True
        assert can_transition(GoalStatus.RUNNING, GoalStatus.PLANNING) is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Retry Logic
# ─────────────────────────────────────────────────────────────────────────────

class TestRetryLogic:
    def test_retry_resets_failed_to_created(self, governor):
        goal = governor.create_goal("Retry me", max_retries=3)
        for s in [GoalStatus.READY, GoalStatus.RUNNING, GoalStatus.FAILED]:
            governor.transition(goal["goal_id"], s)
        updated = governor.retry_goal(goal["goal_id"])
        assert updated["status"] == "CREATED"
        assert updated["retry_count"] == 1

    def test_retry_exhausted_archives_goal(self, governor):
        goal = governor.create_goal("Archive on exhaust", max_retries=2)
        for s in [GoalStatus.READY, GoalStatus.RUNNING, GoalStatus.FAILED]:
            governor.transition(goal["goal_id"], s)
        governor.retry_goal(goal["goal_id"])  # retry_count = 1, CREATED

        # Re-fail and retry again
        store_goal = governor._store.get_goal(goal["goal_id"])
        for s in [GoalStatus.READY, GoalStatus.RUNNING, GoalStatus.FAILED]:
            governor.transition(goal["goal_id"], s)
        final = governor.retry_goal(goal["goal_id"])  # retry_count = 2 >= max_retries=2 → ARCHIVED
        assert final["status"] == "ARCHIVED"
        assert final["retry_count"] == 2

    def test_retry_on_non_failed_raises(self, governor):
        goal = governor.create_goal("Not failed")
        with pytest.raises(GoalTransitionError):
            governor.retry_goal(goal["goal_id"])

    def test_retry_missing_goal_raises(self, governor):
        with pytest.raises(KeyError):
            governor.retry_goal("GOAL-MISSING")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Advance Logic
# ─────────────────────────────────────────────────────────────────────────────

class TestAdvanceLogic:
    def test_advance_created_to_planning(self, governor):
        goal = governor.create_goal("Advance me")
        advanced = governor.advance_goal(goal["goal_id"])
        assert advanced["status"] == "PLANNING"

    def test_advance_planning_to_ready_no_subgoals(self, governor):
        goal = governor.create_goal("Simple goal")
        governor.transition(goal["goal_id"], GoalStatus.PLANNING)
        advanced = governor.advance_goal(goal["goal_id"])
        assert advanced["status"] == "READY"

    def test_advance_planning_blocked_by_incomplete_subgoals(self, governor):
        goal = governor.create_goal("Composite goal")
        governor.transition(goal["goal_id"], GoalStatus.PLANNING)

        # Add an incomplete subgoal
        sub = governor.create_goal("Subgoal", parent_goal_id=goal["goal_id"])
        # Subgoal is in CREATED status — planning should NOT advance to READY
        advanced = governor.advance_goal(goal["goal_id"])
        assert advanced["status"] == "PLANNING"

    def test_advance_planning_ready_when_subgoals_complete(self, governor):
        goal = governor.create_goal("Composite goal")
        governor.transition(goal["goal_id"], GoalStatus.PLANNING)

        sub = governor.create_goal("Subgoal", parent_goal_id=goal["goal_id"])
        # Complete the subgoal
        for s in [GoalStatus.READY, GoalStatus.RUNNING, GoalStatus.COMPLETED]:
            governor.transition(sub["goal_id"], s)

        advanced = governor.advance_goal(goal["goal_id"])
        assert advanced["status"] == "READY"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Goal CRUD Persistence
# ─────────────────────────────────────────────────────────────────────────────

class TestGoalPersistence:
    def test_create_and_retrieve(self, governor, store):
        goal = governor.create_goal("Persist me", priority=8, owner="balu")
        retrieved = store.get_goal(goal["goal_id"])
        assert retrieved is not None
        assert retrieved["title"] == "Persist me"
        assert retrieved["priority"] == 8
        assert retrieved["owner"] == "balu"

    def test_list_goals_filter_by_status(self, governor, store):
        g1 = governor.create_goal("G1")
        g2 = governor.create_goal("G2")
        governor.transition(g1["goal_id"], GoalStatus.PLANNING)

        planning = store.list_goals(status="PLANNING")
        created = store.list_goals(status="CREATED")
        assert any(g["goal_id"] == g1["goal_id"] for g in planning)
        assert any(g["goal_id"] == g2["goal_id"] for g in created)

    def test_list_goals_filter_by_owner(self, governor, store):
        g1 = governor.create_goal("G1", owner="alice")
        g2 = governor.create_goal("G2", owner="bob")
        alice_goals = store.list_goals(owner="alice")
        assert len(alice_goals) == 1
        assert alice_goals[0]["owner"] == "alice"

    def test_subgoal_hierarchy(self, governor, store):
        parent = governor.create_goal("Parent mission")
        sub1 = governor.create_goal("Sub A", parent_goal_id=parent["goal_id"])
        sub2 = governor.create_goal("Sub B", parent_goal_id=parent["goal_id"])
        subgoals = store.list_subgoals(parent["goal_id"])
        assert len(subgoals) == 2
        ids = {s["goal_id"] for s in subgoals}
        assert sub1["goal_id"] in ids
        assert sub2["goal_id"] in ids

    def test_metadata_roundtrip(self, governor, store):
        meta = {"customer": "Acme", "ticket": "INC-1234", "region": "IN"}
        goal = governor.create_goal("Customer goal", metadata=meta)
        retrieved = store.get_goal(goal["goal_id"])
        assert retrieved["metadata"] == meta


# ─────────────────────────────────────────────────────────────────────────────
# 6. Priority Scheduler
# ─────────────────────────────────────────────────────────────────────────────

class TestPriorityScheduler:
    def test_higher_priority_ranks_first(self, scheduler):
        goals = [
            {"goal_id": "A", "status": "READY", "priority": 3, "deadline_utc": None,
             "confidence": 1.0, "retry_count": 0, "max_retries": 3},
            {"goal_id": "B", "status": "READY", "priority": 9, "deadline_utc": None,
             "confidence": 1.0, "retry_count": 0, "max_retries": 3},
        ]
        ranked = scheduler.rank_ready_goals(goals)
        assert ranked[0]["goal_id"] == "B"
        assert ranked[1]["goal_id"] == "A"

    def test_overdue_deadline_increases_score(self, scheduler):
        overdue = {
            "goal_id": "OVERDUE", "status": "READY", "priority": 5,
            "deadline_utc": time.time() - 3600,  # 1 hour ago
            "confidence": 1.0, "retry_count": 0, "max_retries": 3,
        }
        far_future = {
            "goal_id": "FUTURE", "status": "READY", "priority": 5,
            "deadline_utc": time.time() + (10 * 24 * 3600),  # 10 days
            "confidence": 1.0, "retry_count": 0, "max_retries": 3,
        }
        ranked = scheduler.rank_ready_goals([far_future, overdue])
        assert ranked[0]["goal_id"] == "OVERDUE"

    def test_non_ready_goals_passed_through_to_tail(self, scheduler):
        goals = [
            {"goal_id": "R", "status": "READY", "priority": 5, "deadline_utc": None,
             "confidence": 1.0, "retry_count": 0, "max_retries": 3},
            {"goal_id": "NR", "status": "RUNNING", "priority": 9, "deadline_utc": None,
             "confidence": 1.0, "retry_count": 0, "max_retries": 3},
        ]
        ranked = scheduler.rank_ready_goals(goals)
        assert ranked[0]["goal_id"] == "R"
        assert ranked[1]["goal_id"] == "NR"

    def test_retry_penalty_reduces_score(self, scheduler):
        fresh = {
            "goal_id": "FRESH", "status": "READY", "priority": 5, "deadline_utc": None,
            "confidence": 1.0, "retry_count": 0, "max_retries": 3,
        }
        retried = {
            "goal_id": "RETRIED", "status": "READY", "priority": 5, "deadline_utc": None,
            "confidence": 1.0, "retry_count": 2, "max_retries": 3,
        }
        ranked = scheduler.rank_ready_goals([retried, fresh])
        assert ranked[0]["goal_id"] == "FRESH"

    def test_priority_score_injected_in_output(self, scheduler):
        goal = {
            "goal_id": "X", "status": "READY", "priority": 7, "deadline_utc": None,
            "confidence": 0.8, "retry_count": 1, "max_retries": 5,
        }
        ranked = scheduler.rank_ready_goals([goal])
        assert "priority_score" in ranked[0]
        assert 0.0 <= ranked[0]["priority_score"] <= 1.0

    def test_empty_list_returns_empty(self, scheduler):
        assert scheduler.rank_ready_goals([]) == []
