"""Task Execution Runner (Program 5G-6).

Executes individual operator tasks, modifying state variables on success.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from backend.core.planning.task import Operator
from backend.core.execution.execution_state import ExecutionContext

logger = logging.getLogger(__name__)


class TaskRunner:
    """Simulates or triggers real execution hooks for primitive Operators."""

    @staticmethod
    def execute(operator: Operator, context: ExecutionContext) -> Dict[str, Any]:
        """Runs the operator action and applies state effects to context variables."""
        logger.info("Executing operator: %s", operator.name)

        # Check for simulated failures requested in parameters
        if operator.parameters.get("fail_execution", False):
            raise RuntimeError(f"Simulated execution crash on operator '{operator.name}'")

        # Apply state changes to context variables
        context.variables.update(operator.effects)

        # Save return value metadata
        output_data = {
            "node_name": operator.name,
            "status": "Success",
            "timestamp": time.time() if "time" in globals() else 0.0,
        }
        context.outputs[operator.operator_id] = output_data

        return output_data
