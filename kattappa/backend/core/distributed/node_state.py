"""Node State Schema (Program 25.0).

Defines the fields representing a distributed worker node state.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NodeState:
    """Represents registration details, heartbeats, and resource utilizations of a cluster node."""
    node_id: str
    node_name: str
    node_type: str  # e.g., "host", "worker"
    cpu_count: int
    ram_gb: float
    gpu_info: Optional[str] = None
    specializations: List[str] = field(default_factory=list)
    status: str = "alive"  # alive, degraded, offline
    last_heartbeat: float = field(default_factory=time.time)
    
    # Active utilization counters
    cpu_pct: float = 0.0
    ram_pct: float = 0.0
    active_tasks: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "node_type": self.node_type,
            "cpu_count": self.cpu_count,
            "ram_gb": self.ram_gb,
            "gpu_info": self.gpu_info,
            "specializations": self.specializations,
            "status": self.status,
            "last_heartbeat": self.last_heartbeat,
            "cpu_pct": self.cpu_pct,
            "ram_pct": self.ram_pct,
            "active_tasks": self.active_tasks
        }
