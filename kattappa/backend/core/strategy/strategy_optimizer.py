"""Strategy Optimizer: Contextual Rule Compiler (Program 15.0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class StrategyRecommendation:
    """Captures a single contextual routing suggestion with reasoning."""
    planner: str
    model: str
    reasoning: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "planner": self.planner,
            "model": self.model,
            "reasoning": self.reasoning,
        }


class StrategyOptimizer:
    """Compiles contextual decision rules to produce routing recommendations.

    Rules applied in priority order:
      1. Network instability → prefer local models, avoid cloud planners.
      2. Elevated cost overrun history → downgrade model to local_small.
      3. High failure rate on active planner → promote the RiskAware planner.
      4. Low budget → force local_small model regardless of complexity.
    """

    def recommend(self, context: Dict[str, Any]) -> StrategyRecommendation:
        """Produces a strategy recommendation based on environmental context flags."""
        planner = context.get("current_planner", "HTN_Planner")
        model = context.get("current_model", "cloud_reasoning")
        reasoning: List[str] = []

        network_unstable: bool = context.get("network_unstable", False)
        dollar_budget: float = float(context.get("dollar_budget", 1.0))
        planner_failure_rate: float = float(context.get("planner_failure_rate", 0.0))
        cost_overrun_rate: float = float(context.get("cost_overrun_rate", 0.0))

        # Rule 1: Network instability → use local model, switch to Fast Planner
        if network_unstable:
            model = "local_small"
            planner = "Fast_Planner"
            reasoning.append("Network instability detected: routing to local_small model and Fast_Planner.")

        # Rule 2: Frequent cost overruns → demote model to local_small
        if cost_overrun_rate > 0.3 and model != "local_small":
            model = "local_small"
            reasoning.append(
                f"Cost overrun rate {cost_overrun_rate:.0%} exceeds 30%: downgrading model to local_small."
            )

        # Rule 3: Planner failure rate high → switch to RiskAware planner
        if planner_failure_rate > 0.25:
            planner = "RiskAware_Planner"
            reasoning.append(
                f"Planner failure rate {planner_failure_rate:.0%} exceeds 25%: promoting RiskAware_Planner."
            )

        # Rule 4: Hard budget floor → force local model
        if dollar_budget < 0.05 and model != "local_small":
            model = "local_small"
            reasoning.append(
                f"Dollar budget {dollar_budget:.3f} below floor $0.05: forcing local_small model."
            )

        if not reasoning:
            reasoning.append("No contextual anomalies detected. Using current strategy settings.")

        return StrategyRecommendation(planner=planner, model=model, reasoning=reasoning)
