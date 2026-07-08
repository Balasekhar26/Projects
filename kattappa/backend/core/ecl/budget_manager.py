from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ECLBudgetManager:
    """Computes and enforces dynamic token limits, execution cost bounds, and latency limits."""

    @classmethod
    def calculate_budget(cls, priority: str = "MEDIUM") -> Dict[str, Any]:
        """Calculates budget envelopes based on task priority levels."""
        p_upper = priority.upper()

        if p_upper == "HIGH":
            # High priority: allocate more resources
            token_limit = 50000
            max_cost = 5.0  # nominal virtual cost
            time_limit_sec = 60.0
            micro_batch_size = 16
        elif p_upper == "LOW":
            # Low priority: throttle resource utilization
            token_limit = 5000
            max_cost = 0.5
            time_limit_sec = 10.0
            micro_batch_size = 2
        else:
            # MEDIUM / Nominal defaults
            token_limit = 20000
            max_cost = 2.0
            time_limit_sec = 30.0
            micro_batch_size = 8

        logger.debug(
            "Calculated budget: priority=%s, tokens=%d, time_sec=%f, micro_batch=%d",
            p_upper,
            token_limit,
            time_limit_sec,
            micro_batch_size,
        )

        return {
            "token_limit": token_limit,
            "max_cost": max_cost,
            "time_limit_sec": time_limit_sec,
            "micro_batch_size": micro_batch_size,
        }
