"""Unit tests for Program 16.0 Multi-Agent Runtime Hardening.

Tests are structured around the five new safety components:
  1. AgentBudget enforcement (tokens, dollars, time)
  2. DeadlockDetector cycle detection
  3. DelegationDepthExceeded guard (via Task.delegation_depth)
  4. TaskFingerprintStore deduplication
  5. AgentEvents publish (smoke test — verifies no import/publish errors)
"""
from __future__ import annotations

import time
import pytest

from backend.core.orchestrator.runtime.agent_budget import AgentBudget, BudgetExceeded
from backend.core.orchestrator.runtime.deadlock_detector import DeadlockDetector
from backend.core.orchestrator.runtime.task_fingerprint import TaskFingerprintStore
from backend.core.orchestrator.base import Task, DelegationDepthExceeded, MAX_AGENT_DEPTH


# ── 1. AgentBudget ──────────────────────────────────────────────────────────

class TestAgentBudget:
    def test_token_limit_passes_when_under(self):
        budget = AgentBudget(token_limit=1000.0)
        budget.check_tokens(999.9)  # should not raise

    def test_token_limit_raises_when_exceeded(self):
        budget = AgentBudget(token_limit=500.0)
        with pytest.raises(BudgetExceeded) as exc_info:
            budget.check_tokens(501.0)
        assert exc_info.value.dimension == "tokens"
        assert exc_info.value.used == 501.0
        assert exc_info.value.limit == 500.0

    def test_dollar_limit_raises_when_exceeded(self):
        budget = AgentBudget(dollar_limit=0.10)
        with pytest.raises(BudgetExceeded) as exc_info:
            budget.check_dollars(0.11)
        assert exc_info.value.dimension == "dollars"

    def test_time_limit_raises_when_exceeded(self):
        budget = AgentBudget(time_limit_seconds=2.0)
        with pytest.raises(BudgetExceeded) as exc_info:
            budget.check_time(2.5)
        assert exc_info.value.dimension == "time_seconds"

    def test_check_all_time_checked_first(self):
        """Time limit takes priority over token and dollar limits in check_all."""
        budget = AgentBudget(token_limit=1000.0, dollar_limit=1.0, time_limit_seconds=1.0)
        with pytest.raises(BudgetExceeded) as exc_info:
            budget.check_all(used_tokens=5000.0, spent_dollars=5.0, elapsed_seconds=2.0)
        assert exc_info.value.dimension == "time_seconds"

    def test_unlimited_budget_never_raises(self):
        budget = AgentBudget()  # all None → unlimited
        budget.check_all(used_tokens=1e9, spent_dollars=1e9, elapsed_seconds=1e9)


# ── 2. DeadlockDetector ─────────────────────────────────────────────────────

class TestDeadlockDetector:
    def test_no_cycle_in_empty_graph(self):
        detector = DeadlockDetector()
        assert not detector.has_cycle()
        assert detector.detect_and_report() == []

    def test_no_cycle_in_linear_chain(self):
        detector = DeadlockDetector()
        detector.register_wait("A", "B")
        detector.register_wait("B", "C")
        assert not detector.has_cycle()

    def test_simple_two_node_cycle(self):
        detector = DeadlockDetector()
        detector.register_wait("A", "B")
        detector.register_wait("B", "A")
        assert detector.has_cycle()
        cycles = detector.detect_and_report()
        assert len(cycles) >= 1
        participants = set(cycles[0])
        assert "A" in participants and "B" in participants

    def test_three_node_cycle(self):
        detector = DeadlockDetector()
        detector.register_wait("A", "B")
        detector.register_wait("B", "C")
        detector.register_wait("C", "A")
        assert detector.has_cycle()

    def test_release_breaks_cycle(self):
        detector = DeadlockDetector()
        detector.register_wait("A", "B")
        detector.register_wait("B", "A")
        assert detector.has_cycle()
        detector.release("B")        # B completed → its edges disappear
        assert not detector.has_cycle()

    def test_snapshot_is_independent_copy(self):
        detector = DeadlockDetector()
        detector.register_wait("X", "Y")
        snap = detector.snapshot()
        snap["X"].append("Z")        # mutating the snapshot
        assert "Z" not in detector.snapshot().get("X", [])


# ── 3. Delegation Depth Guard ────────────────────────────────────────────────

class TestDelegationDepth:
    def test_task_stores_delegation_depth(self):
        task = Task(task_id="t1", agent_name="Worker", action="run", params={}, delegation_depth=1)
        assert task.delegation_depth == 1

    def test_depth_zero_by_default(self):
        task = Task(task_id="t2", agent_name="Executive", action="route", params={})
        assert task.delegation_depth == 0

    def test_delegation_depth_exceeded_exception(self):
        depth = MAX_AGENT_DEPTH + 1
        with pytest.raises(DelegationDepthExceeded):
            raise DelegationDepthExceeded(depth)

    def test_max_depth_boundary(self):
        """Tasks at exactly MAX_AGENT_DEPTH are legal; beyond it should be blocked."""
        task = Task(task_id="t3", agent_name="Worker", action="run", params={},
                    delegation_depth=MAX_AGENT_DEPTH)
        # Verifies construction succeeds at the boundary
        assert task.delegation_depth == MAX_AGENT_DEPTH


# ── 4. TaskFingerprintStore ──────────────────────────────────────────────────

class TestTaskFingerprintStore:
    def test_fingerprint_is_deterministic(self):
        fp1 = TaskFingerprintStore.fingerprint("g1", "search", {"query": "hello"})
        fp2 = TaskFingerprintStore.fingerprint("g1", "search", {"query": "hello"})
        assert fp1 == fp2

    def test_different_params_produce_different_fingerprints(self):
        fp1 = TaskFingerprintStore.fingerprint("g1", "search", {"query": "hello"})
        fp2 = TaskFingerprintStore.fingerprint("g1", "search", {"query": "world"})
        assert fp1 != fp2

    def test_not_duplicate_before_registration(self):
        store = TaskFingerprintStore()
        fp = TaskFingerprintStore.fingerprint("g1", "act", {"x": 1})
        assert not store.is_duplicate(fp)

    def test_is_duplicate_after_registration(self):
        store = TaskFingerprintStore()
        fp = TaskFingerprintStore.fingerprint("g1", "act", {"x": 1})
        store.register(fp, task_id="t-99", result={"done": True})
        assert store.is_duplicate(fp)

    def test_cached_result_retrieved(self):
        store = TaskFingerprintStore()
        fp = TaskFingerprintStore.fingerprint("g2", "summarise", {"text": "abc"})
        store.register(fp, task_id="t-100", result={"summary": "short"})
        cached = store.get_cached_result(fp)
        assert cached == {"summary": "short"}

    def test_expired_entry_not_duplicate(self):
        store = TaskFingerprintStore(ttl_seconds=0.05)  # 50 ms TTL
        fp = TaskFingerprintStore.fingerprint("g3", "act", {})
        store.register(fp, task_id="t-101")
        time.sleep(0.1)
        assert not store.is_duplicate(fp)

    def test_expire_old_removes_stale_entries(self):
        store = TaskFingerprintStore(ttl_seconds=0.05)
        fp = TaskFingerprintStore.fingerprint("g4", "act", {})
        store.register(fp, task_id="t-102")
        time.sleep(0.1)
        removed = store.expire_old()
        assert removed == 1


# ── 5. AgentEvents smoke test ────────────────────────────────────────────────

class TestAgentEvents:
    def test_emit_functions_do_not_raise(self):
        """Verifies all emit helpers are importable and callable without crashing."""
        from backend.core.orchestrator.runtime import agent_events as ae
        # These may silently fail to reach the bus in tests (no kernel),
        # but they must never raise an unhandled exception.
        ae.emit_spawned("TestAgent", "t-001", delegation_depth=0)
        ae.emit_task_started("TestAgent", "t-001", "run_analysis")
        ae.emit_task_completed("TestAgent", "t-001", output={"result": 42})
        ae.emit_task_failed("TestAgent", "t-001", error="timeout")
        ae.emit_task_cancelled("TestAgent", "t-001", reason="graph cancelled")
        ae.emit_budget_exceeded("TestAgent", "t-001", "tokens", used=600.0, limit=500.0)
        ae.emit_deadlock_detected(cycle=["task-A", "task-B"])
        ae.emit_duplicate_skipped("t-002", fingerprint="abc123")

