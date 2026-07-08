"""Unit and integration tests for Program 5G-6: Stateful Execution Engine.
"""
from __future__ import annotations

import os
import pytest
from typing import List

from backend.core.planning.task import Operator, Plan
from backend.core.planning.plan_graph import PlanCompiler
from backend.core.execution.execution_state import ExecutionSession, ExecutionState, ExecutionContext
from backend.core.execution.events import EventBus, ExecutionEvent
from backend.core.execution.task_runner import TaskRunner
from backend.core.execution.retry import RetryManager
from backend.core.execution.rollback import RollbackManager
from backend.core.execution.checkpoints import CheckpointManager
from backend.core.execution.execution_engine import ExecutionEngine


def test_session_state_machine_transitions():
    """Verifies that ExecutionSession state machine validates valid/invalid status transitions."""
    session = ExecutionSession(session_id="s1", plan_id="p1")
    assert session.status == ExecutionState.PENDING

    session.transition_to(ExecutionState.QUEUED)
    assert session.status == ExecutionState.QUEUED

    session.transition_to(ExecutionState.RUNNING)
    assert session.status == ExecutionState.RUNNING

    # Invalid transitions should raise ValueError
    with pytest.raises(ValueError):
        session.transition_to(ExecutionState.PENDING)


def test_event_bus_publishing():
    """Verifies in-memory pub-sub dispatcher EventBus alerts subscribers of steps events."""
    bus = EventBus.get_instance()
    events_log: List[ExecutionEvent] = []

    def subscriber(ev: ExecutionEvent):
        events_log.append(ev)

    bus.subscribe(subscriber)
    
    ev = ExecutionEvent("TestEvent", "session_123")
    bus.publish(ev)

    assert len(events_log) == 1
    assert events_log[0].event_type == "TestEvent"


def test_task_runner_success_and_simulated_failure():
    """Verifies TaskRunner modifies context variables on success and raises exception on failure."""
    ctx = ExecutionContext(variables={"val": 1})
    op_ok = Operator("ok", "ActionOK", effects={"val": 2})
    op_fail = Operator("fail", "ActionFail", parameters={"fail_execution": True})

    # Success case
    res = TaskRunner.execute(op_ok, ctx)
    assert res["status"] == "Success"
    assert ctx.variables["val"] == 2

    # Failure case
    with pytest.raises(RuntimeError):
        TaskRunner.execute(op_fail, ctx)


def test_retry_policies():
    """Checks linear and exponential backoff delay intervals."""
    assert RetryManager.should_retry("node_1", 1, max_retries=3) is True
    assert RetryManager.should_retry("node_1", 3, max_retries=3) is False

    # Exponential check: 1s, 2s, 4s...
    assert RetryManager.get_backoff_delay(1) == 1.0
    assert RetryManager.get_backoff_delay(2) == 2.0
    assert RetryManager.get_backoff_delay(3) == 4.0

    # Linear check: 1s, 2s, 3s...
    assert RetryManager.get_backoff_delay(2, policy="linear", base_delay=1.5) == 3.0


def test_rollback_undo_lifo_order():
    """Verifies RollbackManager records completions and runs undos in LIFO order."""
    ctx = ExecutionContext(variables={"has_file": True, "uploaded": True})
    
    op_file = Operator("f", "CreateFile", effects={"has_file": True}, parameters={"undo_action": "delete_file"})
    op_upload = Operator("u", "UploadFile", effects={"uploaded": True}, parameters={"undo_action": "remove_upload"})

    rollback = RollbackManager()
    rollback.record_completed(op_file)
    rollback.record_completed(op_upload)

    undone = rollback.execute_rollback(ctx)
    # LIFO: u (UploadFile) should rollback first, then f (CreateFile)
    assert undone == ["undone_UploadFile", "undone_CreateFile"]
    # Reverts variables
    assert ctx.variables["has_file"] is None
    assert ctx.variables["uploaded"] is None


def test_checkpoint_saving_and_hydration(tmp_path):
    """Verifies CheckpointManager serializes and hydrants contexts to disk."""
    checkpoint_dir = str(tmp_path / "checkpoints")
    manager = CheckpointManager(checkpoint_dir)

    session = ExecutionSession("session_abc", "plan_abc", status=ExecutionState.RUNNING, progress=40.0)
    session.completed_nodes.add("node_1")
    context = ExecutionContext(variables={"status": "ok"}, outputs={"node_1": "done"})

    manager.save_checkpoint(session, context)

    # Hydrate
    restored = manager.load_checkpoint("session_abc")
    assert restored is not None
    restored_session, restored_context = restored

    assert restored_session.session_id == "session_abc"
    assert restored_session.progress == 40.0
    assert "node_1" in restored_session.completed_nodes
    assert restored_context.variables["status"] == "ok"
    assert restored_context.outputs["node_1"] == "done"

    # Cleanup
    manager.delete_checkpoint("session_abc")
    assert manager.load_checkpoint("session_abc") is None


def test_execution_engine_full_run_and_failure_rollback():
    """Integration test: HTN plan compiled to DAG, run through ExecutionEngine, triggers rollback on task failures."""
    # Step 0: Backup (Success)
    op_backup = Operator("backup", "BackupAction", effects={"backup_done": True}, parameters={"undo_action": "delete_backup"})
    # Step 1: Deploy (Configured to Fail)
    op_deploy = Operator("deploy", "DeployAction", parameters={"fail_execution": True})

    plan = Plan("p1", "g1", steps=[op_backup, op_deploy])
    graph = PlanCompiler.compile_plan_to_graph(plan)

    engine = ExecutionEngine()
    # Execute (will fail on step 1, trigger rollback on step 0, and fail session)
    session_id = engine.start_execution(graph, {"backup_done": False}, max_retries=1)

    session = engine.sessions[session_id]
    context = engine.contexts[session_id]

    assert session.status == ExecutionState.FAILED
    assert "BackupAction_0" in session.completed_nodes
    assert "DeployAction_1" in session.failed_nodes
    # Variables checked: backup_done should be rolled back to None
    assert context.variables["backup_done"] is None
