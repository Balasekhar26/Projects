"""Reflection Explanation Log Generator (Program 34.0).

Generates comprehensive markdown text logs explaining execution performance,
attributing failures, and analyzing resource efficiency indicators.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend.core.planning.task import Plan


class ReflectionGenerator:
    """Synthesizes text summaries explaining plan execution outcomes."""

    @classmethod
    def generate_reflection(
        cls,
        plan: Plan,
        evaluation: Dict[str, Any],
        failed_step_index: Optional[int] = None,
        failed_operator: Optional[str] = None,
        failure_detail: Optional[str] = None,
    ) -> str:
        """Synthesizes analytical review logs detailing successes or failures."""
        plan_id = plan.plan_id
        is_success = evaluation["is_success"]
        score = evaluation["score"]

        lines = [
            f"# Reflection Summary for Plan: {plan_id}",
            f"**Status**: {'SUCCESS' if is_success else 'FAILURE'}",
            f"**Outcome Score**: {score:.2f}",
            "",
            "## Resource Variance Analysis",
            f"- Expected Cost: {evaluation['expected_cost']:.2f} | Actual Cost: {evaluation['actual_cost']:.2f} (Variance: {evaluation['cost_variance_ratio']:.2%})",
            f"- Expected Duration: {evaluation['expected_duration']:.2f} | Actual Duration: {evaluation['actual_duration']:.2f} (Variance: {evaluation['duration_variance_ratio']:.2%})",
            "",
        ]

        if is_success:
            lines.append("## Blame & Success Attribution")
            lines.append("All plan step postconditions were successfully realized in order.")
            if evaluation["cost_variance_ratio"] < 1.0:
                lines.append("- Cost Efficiency: The execution was budget-positive (below expectation).")
            else:
                lines.append("- Cost Efficiency: The execution exceeded budgeted cost predictions.")
        else:
            lines.append("## Failure Attribution & Critique")
            if failed_operator:
                lines.append(
                    f"Execution crashed at step index `{failed_step_index}` while executing operator `{failed_operator}`."
                )
            else:
                lines.append("Execution failed to materialize the final goal state postconditions.")

            if failure_detail:
                lines.append(f"- **Underlying Error Detail**: {failure_detail}")

            lines.append("")
            lines.append("### Diagnostic Inference")
            if failed_operator:
                lines.append(
                    f"The failure of `{failed_operator}` implies a runtime exception or a local tool malfunction."
                )
            else:
                lines.append(
                    "State variables were modified but failed to match the final postcondition checks."
                )

        return "\n".join(lines)
