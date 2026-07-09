"""Unit tests for Program 32.0: Planning and Execution Reliability Framework.

Verifies checkpoint serialization, resumable execution workflows, step recovery,
and failure diagnosis classification policies.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.core.planning.task import Plan, Operator, PlannerState
from backend.core.planning.checkpoint_recovery import CheckpointRecovery
from backend.core.planning.failure_diagnosis import FailureDiagnosisEngine, FailureType, RecoveryAction
from backend.core.planning.resumable_runtime import ResumableWorkflowRuntime, PreconditionError


@pytest.fixture
def test_plan():
    # Construct 3 simple operators: Step 1 (A->B), Step 2 (B->C), Step 3 (C->D)
    op1 = Operator(
        operator_id="op_1",
        name="step_1",
        preconditions={"state": "A"},
        effects={"state": "B"},
        estimated_cost=1.0,
        estimated_time=1.0,
    )
    op2 = Operator(
        operator_id="op_2",
        name="step_2",
        preconditions={"state": "B"},
        effects={"state": "C"},
        estimated_cost=1.0,
        estimated_time=1.0,
    )
    op3 = Operator(
        operator_id="op_3",
        name="step_3",
        preconditions={"state": "C"},
        effects={"state": "D"},
        estimated_cost=1.0,
        estimated_time=1.0,
    )
    
    return Plan(
        plan_id="test_plan_123",
        goal_id="goal_abc",
        steps=[op1, op2, op3],
        expected_cost=3.0,
        expected_duration=3.0,
        expected_reward=10.0,
        expected_risk=0.1,
        confidence=0.95,
    )


# ── Checkpoint Recovery Tests ─────────────────────────────────────────────────

class TestCheckpointRecovery:
    def test_save_and_load_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = CheckpointRecovery(storage_dir=tmp)
            
            # Save state
            variables = {"state": "B", "counter": 2}
            ckpt_id = engine.save_checkpoint(plan_id="plan_1", step_index=1, variables=variables)
            
            assert ckpt_id.startswith("ckpt_")
            
            # Load and verify
            loaded = engine.load_checkpoint(ckpt_id)
            assert loaded is not None
            assert loaded["plan_id"] == "plan_1"
            assert loaded["step_index"] == 1
            assert loaded["variables"]["state"] == "B"
            assert loaded["variables"]["counter"] == 2
            
            # Clear checkpoint
            engine.clear_checkpoint(ckpt_id)
            assert engine.load_checkpoint(ckpt_id) is None


# ── Failure Diagnosis Engine Tests ────────────────────────────────────────────

class TestFailureDiagnosis:
    def test_diagnose_timeout_error(self):
        err = TimeoutError("Network fetch timed out after 30s")
        failure_type, action, desc = FailureDiagnosisEngine.diagnose_failure(err)
        
        assert failure_type == FailureType.TIMEOUT
        assert action == RecoveryAction.RETRY
        assert "deadline" in desc

    def test_diagnose_permission_error(self):
        err = PermissionError("Write access denied on system config directory")
        failure_type, action, desc = FailureDiagnosisEngine.diagnose_failure(err)
        
        assert failure_type == FailureType.PERMISSION_DENIED
        assert action == RecoveryAction.ESCALATE
        assert "Privilege boundaries" in desc

    def test_diagnose_precondition_error(self):
        err = PreconditionError("Precondition check failed")
        failure_type, action, desc = FailureDiagnosisEngine.diagnose_failure(err)
        
        assert failure_type == FailureType.PRECONDITION_FAILED
        assert action == RecoveryAction.REPLAN
        assert "State variables" in desc

    def test_diagnose_resource_connection_error(self):
        err = ConnectionError("ChromaDB container connection refused")
        failure_type, action, desc = FailureDiagnosisEngine.diagnose_failure(err)
        
        assert failure_type == FailureType.RESOURCE_UNAVAILABLE
        assert action == RecoveryAction.RETRY
        assert "resource unavailable" in desc


# ── Resumable Workflow Runtime Tests ──────────────────────────────────────────

class TestResumableWorkflowRuntime:
    def test_execute_plan_success(self, test_plan):
        with tempfile.TemporaryDirectory() as tmp:
            ckpt_engine = CheckpointRecovery(storage_dir=tmp)
            runtime = ResumableWorkflowRuntime(checkpoint_engine=ckpt_engine)
            
            initial_state = PlannerState(current_goal="test_goal", variables={"state": "A"})
            executed_steps = []
            
            def step_executor(op: Operator):
                executed_steps.append(op.name)

            result = runtime.execute_plan(test_plan, initial_state, step_executor)
            
            assert result["status"] == "completed"
            assert result["variables"]["state"] == "D"
            assert len(executed_steps) == 3
            assert executed_steps == ["step_1", "step_2", "step_3"]

    def test_execute_plan_precondition_failed_returns_diagnosed_checkpoint(self, test_plan):
        with tempfile.TemporaryDirectory() as tmp:
            ckpt_engine = CheckpointRecovery(storage_dir=tmp)
            runtime = ResumableWorkflowRuntime(checkpoint_engine=ckpt_engine)
            
            # Initial state has "state": "A".
            # Step 1 sets "state": "B".
            # Step 2 has preconditions {"state": "B"}, but let's cause an execution failure inside step 2.
            initial_state = PlannerState(current_goal="test_goal", variables={"state": "A"})
            
            def step_executor(op: Operator):
                if op.name == "step_2":
                    raise TimeoutError("Simulated execution timeout")

            result = runtime.execute_plan(test_plan, initial_state, step_executor)
            
            # Step 1 ran and succeeded, state is "B". Step 2 failed and triggered checkpointing.
            assert result["status"] == "failed"
            assert result["step_index"] == 1  # 0-indexed step_2 is index 1
            assert result["variables"]["state"] == "B"
            assert result["failure_type"] == "TIMEOUT"
            assert result["recovery_action"] == "RETRY"
            
            # Get checkpoint saved from step 1 success (points to step 2 as next execution index)
            ckpt_id = result["checkpoint_id"]
            assert ckpt_id is not None
            
            ckpt = ckpt_engine.load_checkpoint(ckpt_id)
            assert ckpt["step_index"] == 1  # resumes from step 2
            assert ckpt["variables"]["state"] == "B"

    def test_resume_plan_from_checkpoint(self, test_plan):
        with tempfile.TemporaryDirectory() as tmp:
            ckpt_engine = CheckpointRecovery(storage_dir=tmp)
            runtime = ResumableWorkflowRuntime(checkpoint_engine=ckpt_engine)
            
            # Pre-populate a checkpoint where step 1 succeeded, state is "B", next index is 1 (step_2)
            ckpt_id = ckpt_engine.save_checkpoint(
                plan_id=test_plan.plan_id,
                step_index=1,
                variables={"state": "B"},
            )
            
            executed_steps = []
            def step_executor(op: Operator):
                executed_steps.append(op.name)

            # Resume
            result = runtime.resume_from_checkpoint(test_plan, ckpt_id, step_executor)
            
            assert result["status"] == "completed"
            assert result["variables"]["state"] == "D"
            # Should have run step_2 and step_3, but NOT step_1 (already completed in checkpoint)
            assert executed_steps == ["step_2", "step_3"]
            
            # Checkpoint should be cleared on success
            assert ckpt_engine.load_checkpoint(ckpt_id) is None
