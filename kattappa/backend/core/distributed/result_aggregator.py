"""Result Aggregator (Program 25.0).

Aggregates execution responses and task statuses from distributed worker nodes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ResultAggregator:
    """Collates finished outputs from parallel workers under unified task envelopes."""

    @classmethod
    def aggregate_results(cls, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merges multiple worker responses.

        Computes overall success, compiles output lists, and sums cost/latencies metrics.
        """
        if not results:
            return {"success": True, "outputs": [], "duration_ms": 0, "cost": 0.0}

        success = True
        merged_outputs = []
        total_duration = 0.0
        total_cost = 0.0

        for r in results:
            # If any sub-task failed, parent context records failure
            if not r.get("success", False):
                success = False

            output_val = r.get("output") or r.get("result") or r.get("message")
            if output_val:
                merged_outputs.append(output_val)

            total_duration += float(r.get("duration_ms", 0.0))
            total_cost += float(r.get("cost", 0.0))

        logger.info(
            "ResultAggregator: Aggregated %d results. Success: %s (cost: %.3f)",
            len(results), success, total_cost
        )

        return {
            "success": success,
            "outputs": merged_outputs,
            "duration_ms": total_duration,
            "cost": round(total_cost, 4)
        }
