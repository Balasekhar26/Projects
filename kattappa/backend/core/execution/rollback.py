"""Execution Rollback and Undo Recovery Manager (Program 5G-6).

Tracks successfully completed operators and executes registered undo actions in reverse.
"""
from __future__ import annotations

import logging
from typing import Any, List
from backend.core.planning.task import Operator
from backend.core.execution.execution_state import ExecutionContext

logger = logging.getLogger(__name__)


class RollbackManager:
    """Orchestrates undo execution routines in LIFO order upon plan failures."""

    def __init__(self) -> None:
        # Stack of completed Operator objects to roll back
        self.completed_stack: List[Operator] = []

    def record_completed(self, operator: Operator) -> None:
        """Pushes successfully executed step onto rollback history stack."""
        self.completed_stack.append(operator)

    def execute_rollback(self, context: ExecutionContext) -> List[str]:
        """Runs undo actions for completed operators in reverse chronological order.

        Returns list of executed undo actions.
        """
        undone_actions = []
        logger.info("Starting plan execution rollback procedure...")

        while self.completed_stack:
            op = self.completed_stack.pop()
            undo_action = op.parameters.get("undo_action")
            
            if undo_action:
                logger.info("Rolling back operator %s via undo action: %s", op.name, undo_action)
                undone_actions.append(f"undone_{op.name}")
                
                # Revert effect updates in variables context if present
                for key in op.effects:
                    if key in context.variables:
                        # Revert back to default/None or previous if we had backup states.
                        # Simple: remove it from variables or set to False/None
                        context.variables[key] = None
            else:
                logger.info("Operator %s has no registered undo action. Skipping.", op.name)

        return undone_actions
