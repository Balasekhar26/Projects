from __future__ import annotations
from typing import Any, Dict

class ObservationEngine:
    """Monitors step execution outputs, gathers logs, and packages raw results for cognitive stores."""

    @staticmethod
    def observe(step_name: str, execution_result: Dict[str, Any]) -> Dict[str, Any]:
        output = execution_result.get("output", "")
        status = execution_result.get("status", "UNKNOWN")
        error = execution_result.get("error")

        # Determine success indicators and confidence
        success = False
        if status == "SUCCESS" or "success" in str(output).lower() or "booked" in str(output).lower():
            success = True

        confidence = 0.99 if success else 0.40

        return {
            "step_name": step_name,
            "success": success,
            "confidence": confidence,
            "extracted_observation": output,
            "error_occurred": error is not None,
            "details": execution_result
        }
