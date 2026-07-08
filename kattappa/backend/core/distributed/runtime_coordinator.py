"""Runtime Coordinator (Program 25.0).

Central entry point coordinates registry mappings, task queues, heartbeat sweeps, and ledger logs.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from backend.core.distributed.node_state import NodeState
from backend.core.distributed.worker_registry import WorkerRegistry
from backend.core.distributed.task_dispatcher import TaskDispatcher
from backend.core.distributed.distributed_ledger import DistributedLedger
from backend.core.distributed.heartbeat_manager import HeartbeatManager

logger = logging.getLogger(__name__)


class RuntimeCoordinator:
    """Orchestrates worker registries, schedules load-balanced tasks, and triggers failovers."""

    def __init__(self) -> None:
        self.registry = WorkerRegistry()
        # Maps task_id -> node_id representing active task locations
        self.active_assignments: Dict[str, str] = {}
        # Maps task_id -> task parameter dictionary
        self.task_cache: Dict[str, Dict[str, Any]] = {}

    def register_node(
        self,
        node_id: str,
        node_name: str,
        cpu_count: int,
        ram_gb: float,
        specializations: List[str]
    ) -> NodeState:
        """Registers a worker node in the cluster pool."""
        node = NodeState(
            node_id=node_id,
            node_name=node_name,
            node_type="worker",
            cpu_count=cpu_count,
            ram_gb=ram_gb,
            specializations=specializations
        )
        self.registry.register_worker(node)
        return node

    def dispatch_task(self, task_id: str, action: str, required_specialization: str) -> Optional[str]:
        """Load-balances and assigns task, recording transaction in the distributed ledger.

        Returns assigned Node ID or None.
        """
        node = TaskDispatcher.select_node_for_task(required_specialization, self.registry)
        if not node:
            logger.warning("RuntimeCoordinator: Cannot dispatch task %s; no specialists available.", task_id)
            return None

        # Cache task configuration details
        self.task_cache[task_id] = {
            "task_id": task_id,
            "action": action,
            "required_specialization": required_specialization
        }

        # Track assignment
        self.active_assignments[task_id] = node.node_id
        node.active_tasks += 1
        
        # Log to ledger
        DistributedLedger.log_assignment(task_id, node.node_id, action)
        return node.node_id

    def complete_task(self, task_id: str) -> None:
        """Clears active assignment tracking upon successful task completion."""
        node_id = self.active_assignments.get(task_id)
        if node_id:
            node = self.registry.get_node(node_id)
            if node:
                node.active_tasks = max(0, node.active_tasks - 1)
            del self.active_assignments[task_id]
            logger.info("RuntimeCoordinator: Completed task '%s' run on node '%s'", task_id, node_id)

    def tick_heartbeat_sweep(self) -> List[str]:
        """Ticks heartbeat audits, triggering failovers for stale nodes."""
        
        def handle_reassign(task_id: str, failed_node_id: str):
            # 1. Fetch task details
            task = self.task_cache.get(task_id)
            if not task:
                return

            # Decrement active tasks count on failed node
            old_node = self.registry.get_node(failed_node_id)
            if old_node:
                old_node.active_tasks = max(0, old_node.active_tasks - 1)

            # 2. Select new node
            new_node = TaskDispatcher.select_node_for_task(task["required_specialization"], self.registry)
            if new_node:
                self.active_assignments[task_id] = new_node.node_id
                new_node.active_tasks += 1
                
                # Log migration
                DistributedLedger.log_migration(
                    task_id=task_id,
                    old_node_id=failed_node_id,
                    new_node_id=new_node.node_id,
                    reason="Node heartbeat timeout"
                )
            else:
                logger.error("RuntimeCoordinator: Failover failed for '%s'; no other workers available.", task_id)

        # Trigger failover sweeps
        migrated = HeartbeatManager.audit_and_failover(
            registry=self.registry,
            active_assignments=self.active_assignments,
            reassign_fn=handle_reassign
        )
        return migrated
