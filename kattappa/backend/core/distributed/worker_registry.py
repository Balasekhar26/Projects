"""Worker Registry (Program 25.0).

Coordinates cluster node configurations, heartbeats, and resource capacities.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional

from backend.core.distributed.node_state import NodeState

logger = logging.getLogger(__name__)


class WorkerRegistry:
    """Provides thread-safe access to registered worker nodes in the distributed cluster."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nodes: Dict[str, NodeState] = {}

    def register_worker(self, node: NodeState) -> None:
        """Adds or updates a node state in the registry."""
        with self._lock:
            self._nodes[node.node_id] = node
            logger.info("WorkerRegistry: Registered worker node '%s' (%s)", node.node_name, node.node_id)

    def deregister_worker(self, node_id: str) -> bool:
        """Removes a worker node from registration."""
        with self._lock:
            if node_id in self._nodes:
                del self._nodes[node_id]
                logger.info("WorkerRegistry: Deregistered worker node '%s'", node_id)
                return True
            return False

    def update_heartbeat(
        self,
        node_id: str,
        cpu_pct: float,
        ram_pct: float,
        active_tasks: int,
        status: str = "alive"
    ) -> bool:
        """Updates utilization parameters and marks node alive."""
        with self._lock:
            node = self._nodes.get(node_id)
            if not node:
                return False
            node.cpu_pct = cpu_pct
            node.ram_pct = ram_pct
            node.active_tasks = active_tasks
            node.status = status
            node.last_heartbeat = time.time()
            return True

    def get_node(self, node_id: str) -> Optional[NodeState]:
        with self._lock:
            return self._nodes.get(node_id)

    def get_active_workers(self) -> List[NodeState]:
        """Returns all registered nodes with active status (alive or degraded)."""
        with self._lock:
            return [n for n in self._nodes.values() if n.status in ("alive", "degraded")]

    def find_specialists(self, capability: str) -> List[NodeState]:
        """Finds active nodes containing the targeted capability specialization."""
        with self._lock:
            specialists = []
            for n in self._nodes.values():
                if n.status in ("alive", "degraded") and capability.lower() in [s.lower() for s in n.specializations]:
                    specialists.append(n)
            return specialists

    def clear(self) -> None:
        with self._lock:
            self._nodes.clear()
