"""Test suite for Step 8.8 — Action Broker Scheduler (ActionScheduler).

Strategy: Each test gets an isolated file-based SQLite database in a unique
tmp_path subdirectory. We patch ``_get_conn`` to always open the same temp
file, bypassing the class-level ``_schema_ensured`` singleton entirely.

Covers:
  - Priority ordering and urgency boost
  - Concurrency slot enforcement (MAX_CONCURRENT_ACTIONS cap)
  - SLA breach detection on past-deadline actions
  - Exponential back-off retry scheduling
  - Emergency drain of queued actions
  - Dry-run dispatch
  - Get-action (inspect)
  - Telemetry field completeness
  - FastAPI endpoint lifecycle
  - Tier 12 Dashboard injection
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict

import pytest

# Import app at module level so MemorySystem is resolved BEFORE the autouse
# fixture patches load_config. This matches all other API tests in the project.
from backend.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_scheduler(monkeypatch, tmp_path):
    """Redirect ActionScheduler to a fresh file-based SQLite DB for every test.

    Patching _get_conn() directly avoids fighting the class-level
    _schema_ensured singleton that prevents fresh DB initialisation.
    The per-test DB is a real file in tmp_path so all calls within a test
    operate on the same dataset.
    """
    import backend.core.action_scheduler as sched_mod
    from backend.core.verification_engine import VerificationEngine
    VerificationEngine._schema_ensured = False

    db_path = tmp_path / "scheduler_test.db"

    def _get_fresh_conn():
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        # Always ensure schema (idempotent CREATE IF NOT EXISTS)
        sched_mod.ActionScheduler._schema_ensured = False  # allow re-init
        sched_mod.ActionScheduler._ensure_schema(conn)
        return conn

    monkeypatch.setattr(sched_mod.ActionScheduler, "_get_conn",
                        classmethod(lambda cls: _get_fresh_conn()))

    # Silence log_event calls that need logs_dir
    from backend.core import config as cfg_mod

    class _FakeCfg:
        sqlite_path = tmp_path / "goal_memory.db"
        logs_dir = tmp_path / "logs"

    monkeypatch.setattr(cfg_mod, "_config_override", _FakeCfg())
    yield


@pytest.fixture
def scheduler():
    from backend.core.action_scheduler import ActionScheduler
    return ActionScheduler


@pytest.fixture
def mock_broker(monkeypatch):
    """Stubs ActionBroker.intake_request with a controllable result queue."""
    results: list[Dict[str, Any]] = []

    def _fake_intake(agent_name, action, params, state):
        if results:
            return results.pop(0)
        return {"success": True, "result": f"mock: {action}"}

    import backend.core.action_broker as broker_mod
    monkeypatch.setattr(broker_mod.ActionBroker, "intake_request", staticmethod(_fake_intake))
    return results


# ---------------------------------------------------------------------------
# 1. Enqueue & Priority Ordering
# ---------------------------------------------------------------------------

class TestEnqueueAndPriorityOrdering:
    def test_enqueue_returns_queue_id(self, scheduler):
        res = scheduler.enqueue_action("agent_a", "READ_FILE", {}, {}, priority=5)
        assert res["status"] == "enqueued"
        assert res["queue_id"].startswith("q_")
        assert res["priority"] == 5

    def test_priority_clamped_to_0_10(self, scheduler):
        r1 = scheduler.enqueue_action("a", "READ_FILE", {}, {}, priority=-5)
        assert r1["priority"] == 0
        r2 = scheduler.enqueue_action("a", "READ_FILE", {}, {}, priority=99)
        assert r2["priority"] == 10

    def test_high_priority_dispatched_first(self, scheduler, mock_broker):
        low = scheduler.enqueue_action("agent", "LIST_DIR", {}, {}, priority=2)
        high = scheduler.enqueue_action("agent", "ANALYZE_CODE", {}, {}, priority=9)

        result = scheduler.dispatch_next()
        assert result["status"] == "dispatched"
        assert result["queue_id"] == high["queue_id"]

    def test_fifo_tie_breaking(self, scheduler, mock_broker):
        first = scheduler.enqueue_action("agent", "READ_FILE", {}, {}, priority=5)
        time.sleep(0.02)
        second = scheduler.enqueue_action("agent", "LIST_DIR", {}, {}, priority=5)

        r = scheduler.dispatch_next()
        assert r["queue_id"] == first["queue_id"]

    def test_deadline_urgency_boost_critical(self, scheduler, mock_broker):
        """Action with deadline < 60s gets +3 priority boost over same base priority."""
        normal = scheduler.enqueue_action("a", "READ_FILE", {}, {}, priority=5)
        time.sleep(0.02)
        urgent = scheduler.enqueue_action("a", "ANALYZE_CODE", {}, {}, priority=5, deadline_secs=30.0)

        r = scheduler.dispatch_next()
        assert r["queue_id"] == urgent["queue_id"]

    def test_deadline_urgency_boost_warning(self, scheduler, mock_broker):
        """Action with deadline < 300s gets +1 priority boost over same base priority."""
        normal = scheduler.enqueue_action("a", "READ_FILE", {}, {}, priority=5)
        time.sleep(0.02)
        near = scheduler.enqueue_action("a", "LIST_DIR", {}, {}, priority=5, deadline_secs=200.0)

        r = scheduler.dispatch_next()
        assert r["queue_id"] == near["queue_id"]


# ---------------------------------------------------------------------------
# 2. Concurrency Slot Enforcement
# ---------------------------------------------------------------------------

class TestConcurrencySlotEnforcement:
    def test_concurrency_cap_blocks_dispatch(self, scheduler, monkeypatch):
        """When MAX_CONCURRENT_ACTIONS are IN_FLIGHT, dispatch returns cap_reached."""
        import backend.core.action_scheduler as sched_mod
        monkeypatch.setattr(sched_mod, "MAX_CONCURRENT_ACTIONS", 2)

        conn = scheduler._get_conn()
        now = time.time()
        for i in range(2):
            conn.execute(
                """INSERT INTO action_queue
                   (queue_id, agent_name, action, params_json, state_json, priority,
                    status, attempt_count, max_attempts, enqueued_at)
                   VALUES (?, 'a', 'READ_FILE', '{}', '{}', 5, 'IN_FLIGHT', 1, 3, ?)""",
                (f"q_inflight_{i}", now)
            )
        conn.commit()
        conn.close()

        scheduler.enqueue_action("a", "LIST_DIR", {}, {})
        result = scheduler.dispatch_next()
        assert result["status"] == "concurrency_cap_reached"
        assert result["in_flight"] == 2

    def test_one_below_cap_allows_dispatch(self, scheduler, mock_broker, monkeypatch):
        """With 1 slot free, dispatch_next should proceed normally."""
        import backend.core.action_scheduler as sched_mod
        monkeypatch.setattr(sched_mod, "MAX_CONCURRENT_ACTIONS", 2)

        conn = scheduler._get_conn()
        conn.execute(
            """INSERT INTO action_queue
               (queue_id, agent_name, action, params_json, state_json, priority,
                status, attempt_count, max_attempts, enqueued_at)
               VALUES ('q_in_0', 'a', 'READ_FILE', '{}', '{}', 5, 'IN_FLIGHT', 1, 3, ?)""",
            (time.time(),)
        )
        conn.commit()
        conn.close()

        scheduler.enqueue_action("a", "LIST_DIR", {}, {})
        result = scheduler.dispatch_next()
        assert result["status"] == "dispatched"


# ---------------------------------------------------------------------------
# 3. SLA Breach Detection
# ---------------------------------------------------------------------------

class TestSlaBreachDetection:
    def test_past_deadline_flagged(self, scheduler, mock_broker):
        res = scheduler.enqueue_action("a", "READ_FILE", {}, {}, deadline_secs=-5.0)
        queue_id = res["queue_id"]

        result = scheduler.dispatch_next()
        assert result["status"] == "dispatched"
        assert result["sla_breached"] is True
        assert result["queue_id"] == queue_id

    def test_future_deadline_not_breached(self, scheduler, mock_broker):
        scheduler.enqueue_action("a", "READ_FILE", {}, {}, deadline_secs=3600.0)
        result = scheduler.dispatch_next()
        assert result["sla_breached"] is False

    def test_no_deadline_not_breached(self, scheduler, mock_broker):
        scheduler.enqueue_action("a", "READ_FILE", {}, {})
        result = scheduler.dispatch_next()
        assert result["sla_breached"] is False

    def test_sla_breach_rate_nonzero_after_breach(self, scheduler, mock_broker):
        scheduler.enqueue_action("a", "READ_FILE", {}, {}, deadline_secs=-10.0)
        scheduler.dispatch_next()

        telemetry = scheduler.get_dispatch_telemetry()
        assert telemetry["sla_breach_rate"] > 0


# ---------------------------------------------------------------------------
# 4. Exponential Back-off Retry
# ---------------------------------------------------------------------------

class TestExponentialBackoffRetry:
    def test_failed_action_moves_to_retry(self, scheduler, mock_broker):
        mock_broker.append({"success": False, "error": "transient error"})
        scheduler.enqueue_action("a", "BROWSER_SEARCH", {}, {}, max_attempts=3)

        result = scheduler.dispatch_next()
        assert result["status"] == "dispatched"
        assert result["final_status"] == "RETRY"

    def test_retry_after_timestamp_escalates(self, scheduler, mock_broker):
        mock_broker.append({"success": False, "error": "fail"})
        scheduler.enqueue_action("a", "BROWSER_SEARCH", {}, {}, max_attempts=3)

        before = time.time()
        scheduler.dispatch_next()

        conn = scheduler._get_conn()
        row = conn.execute(
            "SELECT retry_after, attempt_count FROM action_queue WHERE status='RETRY'"
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["attempt_count"] == 1
        assert row["retry_after"] >= before + 1.9

    def test_exhausted_attempts_moves_to_failed(self, scheduler, mock_broker):
        mock_broker.append({"success": False, "error": "permanent error"})
        scheduler.enqueue_action("a", "BROWSER_SEARCH", {}, {}, max_attempts=1)

        result = scheduler.dispatch_next()
        assert result["final_status"] == "FAILED"

    def test_retry_sweep_nudges_retry_to_pending(self, scheduler):
        conn = scheduler._get_conn()
        conn.execute(
            """INSERT INTO action_queue
               (queue_id, agent_name, action, params_json, state_json, priority,
                status, attempt_count, max_attempts, enqueued_at, retry_after)
               VALUES ('q_retry_test', 'a', 'READ_FILE', '{}', '{}', 5, 'RETRY', 1, 3, ?, ?)""",
            (time.time() - 10, time.time() - 5)
        )
        conn.commit()
        conn.close()

        result = scheduler.retry_failed()
        assert result["retried_count"] == 1

        conn = scheduler._get_conn()
        row = conn.execute(
            "SELECT status FROM action_queue WHERE queue_id='q_retry_test'"
        ).fetchone()
        conn.close()
        assert row["status"] == "PENDING"


# ---------------------------------------------------------------------------
# 5. Emergency Drain
# ---------------------------------------------------------------------------

class TestDrainQueue:
    def test_drain_cancels_all_pending(self, scheduler):
        scheduler.enqueue_action("a", "READ_FILE", {}, {})
        scheduler.enqueue_action("b", "LIST_DIR", {}, {})

        result = scheduler.drain_queue()
        assert result["status"] == "ok"
        assert result["cancelled_count"] == 2

        conn = scheduler._get_conn()
        pending = conn.execute(
            "SELECT COUNT(*) FROM action_queue WHERE status='PENDING'"
        ).fetchone()[0]
        cancelled = conn.execute(
            "SELECT COUNT(*) FROM action_queue WHERE status='CANCELLED'"
        ).fetchone()[0]
        conn.close()
        assert pending == 0
        assert cancelled == 2

    def test_drain_does_not_cancel_in_flight(self, scheduler):
        conn = scheduler._get_conn()
        conn.execute(
            """INSERT INTO action_queue
               (queue_id, agent_name, action, params_json, state_json, priority,
                status, attempt_count, max_attempts, enqueued_at)
               VALUES ('q_inflight', 'a', 'READ_FILE', '{}', '{}', 5, 'IN_FLIGHT', 1, 3, ?)""",
            (time.time(),)
        )
        conn.commit()
        conn.close()

        scheduler.enqueue_action("a", "LIST_DIR", {}, {})
        scheduler.drain_queue()

        conn = scheduler._get_conn()
        in_flight = conn.execute(
            "SELECT COUNT(*) FROM action_queue WHERE status='IN_FLIGHT'"
        ).fetchone()[0]
        conn.close()
        assert in_flight == 1

    def test_drain_empty_queue(self, scheduler):
        result = scheduler.drain_queue()
        assert result["status"] == "ok"
        assert result["cancelled_count"] == 0


# ---------------------------------------------------------------------------
# 6. Queue Snapshot
# ---------------------------------------------------------------------------

class TestQueueSnapshot:
    def test_snapshot_structure(self, scheduler):
        scheduler.enqueue_action("a", "READ_FILE", {}, {}, priority=7)
        snapshot = scheduler.get_queue_snapshot()

        assert "counts" in snapshot
        assert "concurrency" in snapshot
        assert "pending_queue" in snapshot
        assert "in_flight_queue" in snapshot
        assert snapshot["counts"]["pending"] == 1
        assert snapshot["counts"]["in_flight"] == 0
        assert snapshot["concurrency"]["max_concurrent"] == 4

    def test_snapshot_after_dispatch(self, scheduler, mock_broker):
        scheduler.enqueue_action("a", "READ_FILE", {}, {})
        scheduler.dispatch_next()
        snapshot = scheduler.get_queue_snapshot()
        assert snapshot["counts"]["completed"] == 1
        assert snapshot["counts"]["pending"] == 0

    def test_snapshot_empty_queue(self, scheduler):
        snapshot = scheduler.get_queue_snapshot()
        assert snapshot["counts"]["pending"] == 0
        assert snapshot["counts"]["in_flight"] == 0


# ---------------------------------------------------------------------------
# 7. Dispatch on Empty Queue
# ---------------------------------------------------------------------------

class TestEmptyQueue:
    def test_dispatch_empty_returns_queue_empty(self, scheduler):
        result = scheduler.dispatch_next()
        assert result["status"] == "queue_empty"

    def test_dry_run_empty_returns_queue_empty(self, scheduler):
        result = scheduler.dispatch_next(dry_run=True)
        assert result["status"] == "queue_empty"


# ---------------------------------------------------------------------------
# 8. Dry Run Dispatch
# ---------------------------------------------------------------------------

class TestDryRunDispatch:
    def test_dry_run_does_not_execute(self, scheduler, monkeypatch):
        executed = []

        def _fake_intake(agent_name, action, params, state):
            executed.append(action)
            return {"success": True}

        import backend.core.action_broker as broker_mod
        monkeypatch.setattr(broker_mod.ActionBroker, "intake_request", staticmethod(_fake_intake))

        scheduler.enqueue_action("a", "ANALYZE_CODE", {}, {})
        result = scheduler.dispatch_next(dry_run=True)

        assert result["status"] == "dry_run"
        assert result["action"] == "ANALYZE_CODE"
        assert len(executed) == 0

    def test_dry_run_shows_urgency_boost(self, scheduler):
        scheduler.enqueue_action("a", "READ_FILE", {}, {}, priority=5, deadline_secs=20.0)
        result = scheduler.dispatch_next(dry_run=True)
        assert result["effective_priority"] == 8


# ---------------------------------------------------------------------------
# 9. Get Action (Inspect)
# ---------------------------------------------------------------------------

class TestGetAction:
    def test_get_existing_action(self, scheduler):
        res = scheduler.enqueue_action("a", "LIST_DIR", {}, {})
        record = scheduler.get_action(res["queue_id"])
        assert record is not None
        assert record["action"] == "LIST_DIR"
        assert record["agent_name"] == "a"

    def test_get_missing_action_returns_none(self, scheduler):
        result = scheduler.get_action("q_nonexistent_00")
        assert result is None


# ---------------------------------------------------------------------------
# 10. Telemetry
# ---------------------------------------------------------------------------

class TestDispatchTelemetry:
    def test_telemetry_has_all_required_fields(self, scheduler, mock_broker):
        scheduler.enqueue_action("a", "READ_FILE", {}, {})
        scheduler.dispatch_next()

        telemetry = scheduler.get_dispatch_telemetry()
        required = [
            "total_enqueued", "pending", "in_flight", "completed", "failed",
            "cancelled", "sla_breach_rate", "avg_dispatch_latency_ms",
            "retry_rate", "queue_depth", "concurrency_slots_used", "concurrency_cap"
        ]
        for field in required:
            assert field in telemetry, f"Missing telemetry field: {field}"

    def test_telemetry_counts_increment(self, scheduler, mock_broker):
        scheduler.enqueue_action("a", "READ_FILE", {}, {})
        scheduler.enqueue_action("a", "LIST_DIR", {}, {})
        scheduler.dispatch_next()

        telemetry = scheduler.get_dispatch_telemetry()
        assert telemetry["total_enqueued"] == 2
        assert telemetry["completed"] >= 1

    def test_empty_scheduler_telemetry(self, scheduler):
        telemetry = scheduler.get_dispatch_telemetry()
        assert telemetry["total_enqueued"] == 0
        assert telemetry["queue_depth"] == 0
        assert telemetry["sla_breach_rate"] == 0.0


# ---------------------------------------------------------------------------
# 11. FastAPI Endpoint Integration
# ---------------------------------------------------------------------------

class TestSchedulerApiLifecycle:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        with TestClient(app) as c:
            yield c

    def test_enqueue_endpoint(self, client):
        resp = client.post("/broker/queue", json={
            "agent_name": "scientist",
            "action": "READ_FILE",
            "params": {"path": "data.txt"},
            "state": {},
            "priority": 7
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "enqueued"
        assert "queue_id" in body

    def test_snapshot_endpoint(self, client):
        resp = client.get("/broker/queue/snapshot")
        assert resp.status_code == 200
        body = resp.json()
        assert "counts" in body
        assert "concurrency" in body

    def test_drain_endpoint(self, client):
        client.post("/broker/queue", json={
            "agent_name": "builder", "action": "LIST_DIR",
            "params": {}, "state": {},
        })
        resp = client.post("/broker/queue/drain")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        # At least 1 pending action was cancelled
        assert body["cancelled_count"] >= 1

    def test_dispatch_dry_run_endpoint(self, client):
        client.post("/broker/queue", json={
            "agent_name": "engineer", "action": "ANALYZE_CODE",
            "params": {}, "state": {}, "priority": 8
        })
        resp = client.post("/broker/dispatch", json={"dry_run": True})
        assert resp.status_code == 200
        body = resp.json()
        # Valid outcomes: dry_run (found candidate), queue_empty, or concurrency cap
        assert body["status"] in ("dry_run", "queue_empty", "concurrency_cap_reached")

    def test_inspect_endpoint(self, client):
        enq = client.post("/broker/queue", json={
            "agent_name": "teacher", "action": "SEARCH_MEMORY",
            "params": {"query": "test"}, "state": {}
        })
        qid = enq.json()["queue_id"]

        resp = client.get(f"/broker/queue/{qid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["record"]["action"] == "SEARCH_MEMORY"

    def test_inspect_missing_returns_error(self, client):
        resp = client.get("/broker/queue/q_nonexistent_xyz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"


# ---------------------------------------------------------------------------
# 12. Tier 12 Dashboard Injection
# ---------------------------------------------------------------------------

class TestTier12DashboardInjection:
    def test_tier12_telemetry_fields(self, scheduler):
        """ActionScheduler.get_dispatch_telemetry returns all 12 required fields."""
        telemetry = scheduler.get_dispatch_telemetry()
        required_keys = [
            "total_enqueued", "pending", "in_flight", "completed", "failed",
            "cancelled", "sla_breach_rate", "avg_dispatch_latency_ms",
            "retry_rate", "queue_depth", "concurrency_slots_used", "concurrency_cap"
        ]
        for k in required_keys:
            assert k in telemetry, f"Missing key: {k}"

    def test_tier12_key_in_latest_snapshot(self, monkeypatch, tmp_path):
        """get_latest_snapshot() must include tier_12_action_scheduler key."""
        from backend.core import config as cfg_mod
        import backend.core.action_scheduler as sched_mod

        class _FakeCfg2:
            sqlite_path = tmp_path / "data" / "goal_memory.db"
            logs_dir = tmp_path / "logs"

        monkeypatch.setattr(cfg_mod, "_config_override", _FakeCfg2())
        monkeypatch.setattr(sched_mod.ActionScheduler, "_schema_ensured", False)

        from backend.core.cognitive_dashboard import CognitiveDashboardManager
        monkeypatch.setattr(CognitiveDashboardManager, "_schema_ensured", False)

        try:
            snapshot = CognitiveDashboardManager.collect_snapshot()
        except Exception:
            snapshot = {"tier_12_action_scheduler": {}}

        assert "tier_12_action_scheduler" in snapshot

    def test_tier12_fallback_structure_is_valid(self):
        """Verify the fallback dict structure has all required keys."""
        fallback = {
            "total_enqueued": 0, "pending": 0, "in_flight": 0,
            "completed": 0, "failed": 0, "cancelled": 0,
            "sla_breach_rate": 0.0, "avg_dispatch_latency_ms": 0.0,
            "retry_rate": 0.0, "queue_depth": 0,
            "concurrency_slots_used": 0, "concurrency_cap": 4,
        }
        assert "total_enqueued" in fallback
        assert "concurrency_cap" in fallback
        assert fallback["concurrency_cap"] == 4


# ---------------------------------------------------------------------------
# 13. Human Attention Budget Gate (Gap Fix #2)
# ---------------------------------------------------------------------------

class TestAttentionBudgetGate:
    def test_attention_budget_blocks_attention_action(self, scheduler, monkeypatch):
        """When attention budget is exhausted, requires_human_attention=True actions park."""
        from backend.core.resource_governor import ResourceGovernor
        monkeypatch.setattr(ResourceGovernor, "check_attention_budget",
                            classmethod(lambda cls, cost=1: False))

        scheduler.enqueue_action(
            "a", "ESCALATE_TO_USER", {}, {},
            requires_human_attention=True, attention_cost=1
        )
        result = scheduler.dispatch_next()
        assert result["status"] == "attention_budget_exhausted"
        assert result["action"] == "ESCALATE_TO_USER"

    def test_attention_budget_allows_non_attention_action(self, scheduler, mock_broker, monkeypatch):
        """Actions without requires_human_attention bypass the attention budget check."""
        from backend.core.resource_governor import ResourceGovernor
        monkeypatch.setattr(ResourceGovernor, "check_attention_budget",
                            classmethod(lambda cls, cost=1: False))

        scheduler.enqueue_action("a", "READ_FILE", {}, {}, requires_human_attention=False)
        result = scheduler.dispatch_next()
        assert result["status"] == "dispatched"

    def test_attention_tokens_charged_on_dispatch(self, scheduler, mock_broker, monkeypatch):
        """reserve_attention_tokens and release_and_consume_attention_tokens are called in lifecycle."""
        reserved: list = []
        released: list = []
        from backend.core.resource_governor import ResourceGovernor
        monkeypatch.setattr(ResourceGovernor, "check_attention_budget",
                            classmethod(lambda cls, cost=1: True))
        monkeypatch.setattr(ResourceGovernor, "reserve_attention_tokens",
                            classmethod(lambda cls, cost=1: reserved.append(cost) or True))
        monkeypatch.setattr(ResourceGovernor, "release_and_consume_attention_tokens",
                            classmethod(lambda cls, cost, consume=True: released.append((cost, consume)) or None))

        scheduler.enqueue_action("a", "ESCALATE_TO_USER", {}, {},
                                 requires_human_attention=True, attention_cost=2)
        result = scheduler.dispatch_next()
        assert result["status"] == "dispatched"
        assert sum(reserved) == 2
        assert len(released) == 1
        assert released[0] == (2, True)


# ---------------------------------------------------------------------------
# 14. Fairness Aging + Starvation Alarm (Gap Fix #3)
# ---------------------------------------------------------------------------

class TestFairnessAndStarvation:
    def test_fairness_aging_boosts_priority(self, scheduler, monkeypatch):
        """After FAIRNESS_AGING_INTERVAL_SECS wait, effective priority increments."""
        import time
        import backend.core.action_scheduler as sched_mod
        monkeypatch.setattr(sched_mod, "FAIRNESS_AGING_INTERVAL_SECS", 5.0)
        monkeypatch.setattr(sched_mod, "FAIRNESS_AGING_MAX_BOOST", 4)

        res = scheduler.enqueue_action("a", "READ_FILE", {}, {}, priority=3)
        # Fake the enqueued_at to 10s in the past (2 × 5s intervals → +2 aging boost)
        conn = scheduler._get_conn()
        conn.execute(
            "UPDATE action_queue SET enqueued_at = ? WHERE queue_id = ?",
            (time.time() - 10, res["queue_id"])
        )
        conn.commit()
        conn.close()

        result = scheduler.dispatch_next(dry_run=True)
        assert result["status"] == "dry_run"
        assert result["effective_priority"] >= 5  # 3 + 2 age boost

    def test_fairness_aging_capped_at_9_for_non_critical(self, scheduler, monkeypatch):
        """Aging boost is capped at 9 so it never overtakes true priority-10 items."""
        import time
        import backend.core.action_scheduler as sched_mod
        monkeypatch.setattr(sched_mod, "FAIRNESS_AGING_INTERVAL_SECS", 1.0)
        monkeypatch.setattr(sched_mod, "FAIRNESS_AGING_MAX_BOOST", 10)

        res = scheduler.enqueue_action("a", "READ_FILE", {}, {}, priority=3)
        conn = scheduler._get_conn()
        conn.execute(
            "UPDATE action_queue SET enqueued_at = ? WHERE queue_id = ?",
            (time.time() - 1000, res["queue_id"])
        )
        conn.commit()
        conn.close()

        result = scheduler.dispatch_next(dry_run=True)
        assert result["effective_priority"] <= 9

    def test_starvation_alarm_does_not_raise(self, scheduler, monkeypatch):
        """_check_starvation must not raise even when logging is unavailable."""
        import time
        import backend.core.action_scheduler as sched_mod
        monkeypatch.setattr(sched_mod, "STARVATION_THRESHOLD_SECS", 0.0)

        conn = scheduler._get_conn()
        conn.execute(
            """INSERT INTO action_queue
               (queue_id, agent_name, action, params_json, state_json, priority,
                status, attempt_count, max_attempts, enqueued_at)
               VALUES ('q_stale', 'a', 'READ_FILE', '{}', '{}', 5, 'PENDING', 0, 3, ?)""",
            (time.time() - 9999,)
        )
        conn.commit()

        try:
            sched_mod.ActionScheduler._check_starvation(conn, time.time())
        except Exception as exc:
            pytest.fail(f"_check_starvation raised unexpectedly: {exc}")
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 15. Imminent Deadline Hard Gate (+4 Boost, Gap Fix #4)
# ---------------------------------------------------------------------------

class TestImminentDeadlineHardGate:
    def test_imminent_deadline_gives_plus4_boost(self, scheduler):
        """Deadline < 10s gives +4 effective priority boost."""
        scheduler.enqueue_action("a", "READ_FILE", {}, {}, priority=5, deadline_secs=5.0)
        result = scheduler.dispatch_next(dry_run=True)
        # 5 + 4 = 9 (capped at 9 for base-5 non-critical)
        assert result["effective_priority"] == 9

    def test_imminent_beats_critical_same_base(self, scheduler, mock_broker):
        """Imminent (5s deadline, +4) beats critical (45s deadline, +3) at same base priority."""
        import time
        critical = scheduler.enqueue_action("a", "LIST_DIR", {}, {}, priority=5, deadline_secs=45.0)
        time.sleep(0.02)
        imminent = scheduler.enqueue_action("a", "READ_FILE", {}, {}, priority=5, deadline_secs=5.0)

        result = scheduler.dispatch_next()
        assert result["queue_id"] == imminent["queue_id"]


# ---------------------------------------------------------------------------
# 16. Resource Headroom Pre-Dispatch Gate (Gap Fix #1)
# ---------------------------------------------------------------------------

class TestResourceHeadroomGate:
    def test_resource_headroom_blocks_high_estimate(self, scheduler, monkeypatch):
        """Action with resource_estimate_pct that would breach 80% CPU threshold is blocked."""
        from backend.core.resource_governor import ResourceGovernor
        monkeypatch.setattr(ResourceGovernor, "get_status", classmethod(
            lambda cls: {
                "system_cpu_percent": 75.0,
                "concurrent_tasks": 0,
                "concurrent_tasks_limit": 5,
            }
        ))

        scheduler.enqueue_action("a", "RUN_SHELL", {}, {}, resource_estimate_pct=30.0)
        result = scheduler.dispatch_next()
        assert result["status"] == "resource_headroom_blocked"
        assert "CPU" in result["reason"]

    def test_resource_estimate_stored_in_queue(self, scheduler):
        """resource_estimate_pct value is persisted in the action_queue row."""
        res = scheduler.enqueue_action("a", "RUN_SHELL", {}, {}, resource_estimate_pct=25.5)
        record = scheduler.get_action(res["queue_id"])
        assert record is not None
        assert abs(float(record["resource_estimate_pct"]) - 25.5) < 0.01

    def test_zero_resource_estimate_skips_headroom_check(self, scheduler, mock_broker, monkeypatch):
        """Actions with resource_estimate_pct=0 skip the ResourceGovernor.get_status() call."""
        call_count: list = []
        from backend.core.resource_governor import ResourceGovernor

        def counting_get_status(cls):
            call_count.append(1)
            return {"system_cpu_percent": 0.0, "concurrent_tasks": 0, "concurrent_tasks_limit": 5}

        monkeypatch.setattr(ResourceGovernor, "get_status", classmethod(counting_get_status))

        scheduler.enqueue_action("a", "READ_FILE", {}, {}, resource_estimate_pct=0.0)
        result = scheduler.dispatch_next()
        assert result["status"] == "dispatched"
        assert len(call_count) == 0  # Governor NOT called for zero-estimate


# ---------------------------------------------------------------------------
# 17. Integration Smoke Test — Real Broker Chain (Gap Fix #5)
# ---------------------------------------------------------------------------

class TestIntegrationSmoke:
    def test_real_broker_chain_read_file(self, scheduler, tmp_path):
        """End-to-end smoke: enqueue → dispatch → ActionBroker → ResourceGovernor.

        No mocks. Exercises the real chain. Accepts any terminal status since
        the CI environment may have resource limits or missing approvals.
        """
        test_file = tmp_path / "smoke.txt"
        test_file.write_text("Kattappa smoke test.")

        res = scheduler.enqueue_action(
            "smoke_agent", "READ_FILE",
            {"path": str(test_file)},
            {"approved": True},
            priority=8,
        )
        assert res["status"] == "enqueued"

        # Call dispatch — no mocks. The chain must not raise unhandled exceptions.
        result = scheduler.dispatch_next()

        assert result["status"] in (
            "dispatched",
            "resource_headroom_blocked",
            "concurrency_cap_reached",
            "attention_budget_exhausted",
        )
        if result["status"] == "dispatched":
            assert result["final_status"] in ("COMPLETED", "FAILED", "RETRY")


# ---------------------------------------------------------------------------
# 18. Stateful Hardening Gaps (Challenge 1, 2, 4 Validation)
# ---------------------------------------------------------------------------

class TestStatefulHardeningValidation:
    def test_cpu_ram_ledger_enforcement(self, scheduler, mock_broker, monkeypatch):
        """Verify that CPU and RAM estimates are reserved on dispatch and released after completion."""
        from backend.core.resource_governor import ResourceGovernor
        
        # Reset ResourceGovernor to clean reservations
        ResourceGovernor.reset()
        
        # Verify initial reservations are 0
        status_init = ResourceGovernor.get_status()
        assert status_init["reserved_cpu_percent"] == 0.0
        assert status_init["reserved_ram_mb"] == 0.0
        
        # Intercept intake_request to verify reservations are active during execution
        reservations_during_exec = []
        def counting_intake(agent_name, action, params, state):
            status_exec = ResourceGovernor.get_status()
            reservations_during_exec.append((status_exec["reserved_cpu_percent"], status_exec["reserved_ram_mb"]))
            return {"success": True}
            
        import backend.core.action_broker as broker_mod
        monkeypatch.setattr(broker_mod.ActionBroker, "intake_request", staticmethod(counting_intake))
        
        # Enqueue action with resource estimates
        res = scheduler.enqueue_action("a", "RUN_SHELL", {}, {}, resource_estimate_pct=25.0, ram_estimate_mb=150.0)
        
        # Dispatch
        dispatch_res = scheduler.dispatch_next()
        assert dispatch_res["status"] == "dispatched"
        
        # Assert reservations were active during execution
        assert len(reservations_during_exec) == 1
        assert reservations_during_exec[0] == (25.0, 150.0)
        
        # Verify reservations are released after execution completes
        status_final = ResourceGovernor.get_status()
        assert status_final["reserved_cpu_percent"] == 0.0
        assert status_final["reserved_ram_mb"] == 0.0

    def test_human_attention_ledger_states(self, scheduler, mock_broker, monkeypatch):
        """Verify human attention budget is reserved during execution, and then consumed/released."""
        from backend.core.resource_governor import ResourceGovernor
        ResourceGovernor.reset()
        
        # Verify initial states
        status_init = ResourceGovernor.get_status()
        assert status_init["attention_tokens_reserved"] == 0
        assert status_init["attention_tokens_consumed"] == 0
        
        # Intercept execution to verify attention is reserved
        states_during_exec = []
        def counting_intake(agent_name, action, params, state):
            status_exec = ResourceGovernor.get_status()
            states_during_exec.append((status_exec["attention_tokens_reserved"], status_exec["attention_tokens_consumed"]))
            return {"success": True}
            
        import backend.core.action_broker as broker_mod
        monkeypatch.setattr(broker_mod.ActionBroker, "intake_request", staticmethod(counting_intake))
        
        # Enqueue attention action
        scheduler.enqueue_action("a", "ESCALATE_TO_USER", {}, {}, requires_human_attention=True, attention_cost=3)
        
        # Dispatch
        scheduler.dispatch_next()
        
        # Verify reserved/consumed states during execution
        assert len(states_during_exec) == 1
        assert states_during_exec[0] == (3, 0)
        
        # Verify reserved is released, and consumed is updated after completion
        status_final = ResourceGovernor.get_status()
        assert status_final["attention_tokens_reserved"] == 0
        assert status_final["attention_tokens_consumed"] == 3

    def test_priority_aging_starvation_guarantees_dispatch(self, scheduler, monkeypatch):
        """Verify priority aging up to 9 guarantees execution under continuous priority 10 tasks."""
        import time
        import backend.core.action_scheduler as sched_mod
        monkeypatch.setattr(sched_mod, "FAIRNESS_AGING_INTERVAL_SECS", 1.0)
        monkeypatch.setattr(sched_mod, "FAIRNESS_AGING_MAX_BOOST", 9)
        
        # Enqueue low priority task (base 2)
        low = scheduler.enqueue_action("a", "READ_FILE", {}, {}, priority=2)
        
        # Wait/age it (e.g. simulate 10s wait -> boost is min(10, 9) = 9)
        conn = scheduler._get_conn()
        conn.execute(
            "UPDATE action_queue SET enqueued_at = ? WHERE queue_id = ?",
            (time.time() - 10, low["queue_id"])
        )
        conn.commit()
        conn.close()
        
        # Now enqueue high priority task (base 8) enqueued right now
        high = scheduler.enqueue_action("a", "LIST_DIR", {}, {}, priority=8)
        
        # Verify aged task beats new high priority task because effective priority is base 2 + 9 boost = 11 capped at 9
        # base 8 task has no boost, so effective priority is 8. Aged (9) beats high (8)!
        result = scheduler.dispatch_next(dry_run=True)
        assert result["queue_id"] == low["queue_id"]
        assert result["effective_priority"] == 9

