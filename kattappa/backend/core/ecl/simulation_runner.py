from __future__ import annotations

import logging
from typing import Any, Dict, List

from backend.core.simulation_engine import SimulationEngine

logger = logging.getLogger(__name__)


class ECLSimulationRunner:
    """Wrapper to evaluate plan branches via counterfactual World Model simulations."""

    @classmethod
    def evaluate_viability(
        cls,
        goal_title: str,
        tasks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Runs simulations on candidate plan branches and returns evaluation metrics."""
        # Setup candidate plans (e.g. baseline and high-caution variants)
        baseline_plan = {
            "id": "baseline_branch",
            "steps": tasks,
        }

        # Caution variant: inserts verification checks before any risk steps
        caution_steps = []
        for step in tasks:
            action = step.get("action", "").lower()
            if any(w in action for w in ["delete", "remove", "wipe", "rm"]):
                caution_steps.append({
                    "task_id": f"verify_{step.get('task_id', 'step')}",
                    "agent_name": "SafetyGate",
                    "action": "verify_preconditions",
                    "params": {"target": step.get("params", {}).get("target", "system")},
                })
            caution_steps.append(step)

        caution_plan = {
            "id": "caution_branch",
            "steps": caution_steps,
        }

        candidates = [baseline_plan, caution_plan]
        world_state_context = {"goal_title": goal_title}

        try:
            results = SimulationEngine.simulate_plans(candidates, world_state_context)
            # Find the best branch based on simulation output
            best_branch = results[0] if results else None
            
            branch_reports = []
            for r in results:
                branch_reports.append({
                    "branch_id": r.branch_id,
                    "expected_utility": r.expected_utility,
                    "predicted_risk": r.predicted_risk,
                    "completion_probability": r.completion_probability,
                    "reason": r.reason,
                })

            return {
                "success": True,
                "best_branch_id": best_branch.branch_id if best_branch else "baseline_branch",
                "viability_score": best_branch.expected_utility if best_branch else 0.8,
                "predicted_risk": best_branch.predicted_risk if best_branch else 0.1,
                "branch_reports": branch_reports,
            }
        except Exception as exc:
            logger.error("ECL Counterfactual Simulation failed: %s", exc)
            return {
                "success": False,
                "best_branch_id": "baseline_branch",
                "viability_score": 0.5,
                "predicted_risk": 0.5,
                "branch_reports": [],
            }
