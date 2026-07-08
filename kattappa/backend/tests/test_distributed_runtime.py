"""Unit tests for Program 25.0: Distributed Runtime.

Verifies node registrations, capability load-balancing dispatcher selections,
heartbeat sweeps, task migrations, result aggregations, and transaction ledgers.
"""
from __future__ import annotations

import time
import pytest
from unittest.mock import patch

from backend.core.distributed.node_state import NodeState
from backend.core.distributed.worker_registry import WorkerRegistry
from backend.core.distributed.task_dispatcher import TaskDispatcher
from backend.core.distributed.result_aggregator import ResultAggregator
from backend.core.distributed.distributed_ledger import DistributedLedger
from backend.core.distributed.heartbeat_manager import HeartbeatManager
from backend.core.distributed.runtime_coordinator import RuntimeCoordinator


@pytest.fixture(autouse=True)
def clean_ledgers():
    DistributedLedger.reset()
    yield
    DistributedLedger.reset()


# ── 1. Registry and Specializations Tests ─────────────────────────────────────

class TestWorkerRegistry:
    def test_node_registration_and_specialist_lookup(self):
        registry = WorkerRegistry()
        
        n1 = NodeState("node-1", "Planner Node", "worker", 4, 16.0, specializations=["planner"])
        n2 = NodeState("node-2", "Vision Node", "worker", 8, 32.0, specializations=["perception"])
        
        registry.register_worker(n1)
        registry.register_worker(n2)

        # Specialist matching
        planners = registry.find_specialists("planner")
        assert len(planners) == 1
        assert planners[0].node_id == "node-1"

        visions = registry.find_specialists("perception")
        assert len(visions) == 1
        assert visions[0].node_id == "node-2"


# ── 2. Load-Balancing Task Dispatcher Tests ───────────────────────────────────

class TestTaskDispatcher:
    def test_select_least_loaded_specialist(self):
        registry = WorkerRegistry()

        # 2 Planners. Node 1 is busy with 2 tasks, Node 2 has 0 tasks.
        n1 = NodeState("node-1", "Busy Planner", "worker", 4, 16.0, specializations=["planner"], active_tasks=2)
        n2 = NodeState("node-2", "Free Planner", "worker", 4, 16.0, specializations=["planner"], active_tasks=0)

        registry.register_worker(n1)
        registry.register_worker(n2)

        selected = TaskDispatcher.select_node_for_task("planner", registry)
        assert selected is not None
        assert selected.node_id == "node-2"  # Should route to least loaded node!


# ── 3. Result Aggregator Tests ────────────────────────────────────────────────

class TestResultAggregator:
    def test_aggregate_subtask_results(self):
        results = [
            {"success": True, "result": "Compiled backend", "duration_ms": 1500, "cost": 0.01},
            {"success": True, "result": "Compiled frontend", "duration_ms": 2500, "cost": 0.02},
            {"success": False, "result": "Linker error", "duration_ms": 500, "cost": 0.005}
        ]

        report = ResultAggregator.aggregate_results(results)
        
        assert report["success"] is False  # one failed task
        assert len(report["outputs"]) == 3
        assert "Linker error" in report["outputs"]
        assert report["duration_ms"] == 4500
        assert report["cost"] == 0.035


# ── 4. Distributed Ledger Logging Tests ───────────────────────────────────────

class TestDistributedLedger:
    def test_log_assignment_and_migration(self):
        DistributedLedger.log_assignment("task-99", "node-1", "ExecuteQuery")
        DistributedLedger.log_migration("task-99", "node-1", "node-2", "Heartbeat timeout")

        history = DistributedLedger.get_task_assignments("task-99")
        assert len(history) == 2
        assert history[0]["status"] == "assigned"
        assert history[0]["node_id"] == "node-1"
        assert history[1]["status"] == "migrated"
        assert history[1]["old_node_id"] == "node-1"
        assert history[1]["new_node_id"] == "node-2"


# ── 5. Heartbeat Staleness & Failover Tests ───────────────────────────────────

class TestHeartbeatManager:
    def test_node_heartbeat_timeout_failover(self):
        coordinator = RuntimeCoordinator()

        # Register workers
        n1 = coordinator.register_node("node-1", "Planner Node", 4, 16.0, ["planner"])
        n2 = coordinator.register_node("node-2", "Backup Node", 4, 16.0, ["planner"])

        # Dispatch task to node-1
        coordinator.dispatch_task("task-50", "RunPlanning", "planner")
        assert coordinator.active_assignments["task-50"] == "node-1"
        assert n1.active_tasks == 1

        # Tick immediate -> no timeout
        migrated_none = coordinator.tick_heartbeat_sweep()
        assert len(migrated_none) == 0
        assert n1.status == "alive"

        # Mock time forward by 35 seconds to trigger timeout on node-1
        # Set node-2 last heartbeat to current time so it remains alive
        n2.last_heartbeat = time.time() + 35.0
        with patch("time.time", return_value=time.time() + 35.0):
            migrated = coordinator.tick_heartbeat_sweep()
            assert len(migrated) == 1
            assert migrated[0] == "task-50"
            assert n1.status == "offline"
            # Task should be migrated to node-2!
            assert coordinator.active_assignments["task-50"] == "node-2"
            assert n1.active_tasks == 0
            assert n2.active_tasks == 1
