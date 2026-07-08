"""Heartbeat Manager (Program 25.0).

Audits node heartbeat periods and triggers failover task migrations when workers timeout.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List

from backend.core.distributed.worker_registry import WorkerRegistry
from backend.core.distributed.distributed_ledger import DistributedLedger

logger = logging.getLogger(__name__)


class HeartbeatManager:
    """Monitors worker status heartbeats and coordinates task recovery actions."""

    HEARTBEAT_TIMEOUT_SECONDS = 30.0

    @classmethod
    def audit_and_failover(
        cls,
        registry: WorkerRegistry,
        active_assignments: Dict[str, str],  # task_id -> assigned_node_id
        reassign_fn: Callable[[str, str], Any]  # reassign_fn(task_id, failed_node_id)
    ) -> List[str]:
        """Checks for stale heartbeats. Marks dead nodes offline and triggers task failovers.

        reassign_fn: callback triggered when task needs reassignment.
        Returns list of task IDs that migrated.
        """
        now = time.time()
        dead_nodes = []
        
        # Lock registry and check heartbeat delta
        with registry._lock:
            for node_id, node in registry._nodes.items():
                if node.status != "offline" and now - node.last_heartbeat > cls.HEARTBEAT_TIMEOUT_SECONDS:
                    node.status = "offline"
                    dead_nodes.append(node_id)
                    logger.warning("HeartbeatManager: Node '%s' (%s) timed out; marked offline.", node.node_name, node_id)

        if not dead_nodes:
            return []

        migrated_tasks = []
        # Check active assignments associated with dead nodes
        for task_id, node_id in list(active_assignments.items()):
            if node_id in dead_nodes:
                logger.warning("HeartbeatManager: Failover triggered for task '%s' assigned to dead node '%s'", task_id, node_id)
                # Reassign task
                try:
                    reassign_fn(task_id, node_id)
                    migrated_tasks.append(task_id)
                except Exception as e:
                    logger.error("HeartbeatManager: Failed failover re-assignment for task '%s' — %s", task_id, e)

        return migrated_tasks
