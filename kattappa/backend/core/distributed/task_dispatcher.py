"""Task Dispatcher (Program 25.0).

Load-balances and schedules parallel workflow tasks across matching cluster specialists.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.distributed.node_state import NodeState
from backend.core.distributed.worker_registry import WorkerRegistry

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """Routes execution commands to optimal nodes based on load and specialization constraints."""

    @classmethod
    def select_node_for_task(
        cls,
        required_specialization: str,
        registry: WorkerRegistry
    ) -> Optional[NodeState]:
        """Least-loaded selection among specialists for the required task.

        Returns NodeState or None if no workers match.
        """
        # Find specialists
        candidates = registry.find_specialists(required_specialization)
        if not candidates:
            # Fallback to any active worker node
            candidates = registry.get_active_workers()

        if not candidates:
            logger.warning("TaskDispatcher: No active candidate nodes found in registry.")
            return None

        # Choose the node with the fewest active tasks
        # If active tasks are equal, choose the one with the lowest CPU utilization
        candidates.sort(key=lambda n: (n.active_tasks, n.cpu_pct))
        selected = candidates[0]
        
        logger.info(
            "TaskDispatcher: Dispatched task requiring '%s' to node '%s' (active tasks: %d)",
            required_specialization, selected.node_name, selected.active_tasks
        )
        return selected
