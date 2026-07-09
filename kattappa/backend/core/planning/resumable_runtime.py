"""Resumable Workflow Runtime (Program 32.0).

Executes HTN-decomposed plans step-by-step, validates preconditions, applies
operator effects, writes checkpoints, and supports resume execution from checkpoints.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from backend.core.planning.task import Plan, Operator, PlannerState
from backend.core.planning.checkpoint_recovery import CheckpointRecovery
from backend.core.planning.failure_diagnosis import FailureDiagnosisEngine, RecoveryAction

logger = logging.getLogger(__name__)


class PreconditionError(ValueError):
    """Raised when task preconditions are violated prior to step execution."""


class ResumableWorkflowRuntime:
    """Orchestrates plan step runs, saves checkpoints, and handles failures."""

    def __init__(
        self,
        checkpoint_engine: Optional[CheckpointRecovery] = None,
        diagnosis_engine: Optional[FailureDiagnosisEngine] = None,
    ) -> None:
        self.checkpoints = checkpoint_engine or CheckpointRecovery()
        self.diagnosis = diagnosis_engine or FailureDiagnosisEngine()

    def execute_plan(
        self,
        plan: Plan,
        state: PlannerState,
        step_executor: Callable[[Operator], None],
    ) -> Dict[str, Any]:
        """Runs the entire plan from the start (step_index=0)."""
        return self._run_loop(plan, state.variables, 0, step_executor)

    def resume_from_checkpoint(
        self,
        plan: Plan,
        checkpoint_id: str,
        step_executor: Callable[[Operator], None],
    ) -> Dict[str, Any]:
        """Loads checkpoint parameters and resumes execution from saved step_index."""
        ckpt = self.checkpoints.load_checkpoint(checkpoint_id)
        if not ckpt:
            raise KeyError(f"Checkpoint ID not found: {checkpoint_id}")

        start_step = ckpt["step_index"]
        variables = dict(ckpt["variables"])

        logger.info(
            f"Resuming plan {plan.plan_id} from step {start_step} (checkpoint {checkpoint_id})"
        )
        return self._run_loop(plan, variables, start_step, step_executor, initial_checkpoint_id=checkpoint_id)

    def _run_loop(
        self,
        plan: Plan,
        variables: Dict[str, Any],
        start_step: int,
        step_executor: Callable[[Operator], None],
        initial_checkpoint_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes steps sequentially starting from start_step."""
        current_vars = dict(variables)
        steps = plan.steps
        checkpoint_id = None

        for idx in range(start_step, len(steps)):
            op = steps[idx]
            
            # 1. Validate preconditions
            preconditions_met = all(current_vars.get(k) == v for k, v in op.preconditions.items())
            if not preconditions_met:
                err = PreconditionError(
                    f"Precondition check failed for operator {op.name} at step {idx}"
                )
                failure_type, action, desc = self.diagnosis.diagnose_failure(err)
                return {
                    "status": "failed",
                    "step_index": idx,
                    "failed_operator": op.name,
                    "variables": current_vars,
                    "checkpoint_id": checkpoint_id or initial_checkpoint_id,
                    "failure_type": failure_type.value,
                    "recovery_action": action.value,
                    "detail": desc,
                }

            # 2. Invoke operator
            try:
                step_executor(op)
            except Exception as e:
                failure_type, action, desc = self.diagnosis.diagnose_failure(e)
                return {
                    "status": "failed",
                    "step_index": idx,
                    "failed_operator": op.name,
                    "variables": current_vars,
                    "checkpoint_id": checkpoint_id or initial_checkpoint_id,
                    "failure_type": failure_type.value,
                    "recovery_action": action.value,
                    "detail": desc,
                }

            # 3. Apply operator effects
            current_vars.update(op.effects)

            # 4. Save checkpoint (point to the NEXT step to execute)
            checkpoint_id = self.checkpoints.save_checkpoint(
                plan_id=plan.plan_id,
                step_index=idx + 1,
                variables=current_vars,
            )

        # Clean final checkpoint on full success
        if checkpoint_id:
            self.checkpoints.clear_checkpoint(checkpoint_id)
        if initial_checkpoint_id:
            self.checkpoints.clear_checkpoint(initial_checkpoint_id)

        return {
            "status": "completed",
            "variables": current_vars,
            "checkpoint_id": None,
        }
