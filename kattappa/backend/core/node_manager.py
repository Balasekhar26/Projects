"""Node Manager (Step 9.1 & 9.2).

Manages the registration, heartbeats, and status monitoring of distributed worker nodes.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from backend.core.action_scheduler import ActionScheduler
from backend.core.logger import log_event


class NodeManager:
    """Manages the distributed Node Registry and Node Heartbeats."""

    # In-memory registry of active WebSocket connections for alive nodes
    # Map of node_id -> (WebSocket, Loop)
    _connections: Dict[str, Any] = {}

    @classmethod
    def register_connection(cls, node_id: str, websocket: Any) -> None:
        """Register an active WebSocket connection for a node."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        cls._connections[node_id] = (websocket, loop)

    @classmethod
    def deregister_connection(cls, node_id: str) -> None:
        """Deregister a WebSocket connection for a node."""
        if node_id in cls._connections:
            del cls._connections[node_id]

    @classmethod
    def get_connection(cls, node_id: str) -> Optional[tuple[Any, Any]]:
        """Retrieve the WebSocket connection and loop for a node."""
        return cls._connections.get(node_id)

    @classmethod
    def register_node(
        cls,
        node_id: str,
        node_name: str,
        node_type: str,
        cpu_logical: int,
        ram_gb: float,
        gpu_info: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
    ) -> None:
        """Register or update node registration details."""
        capabilities_json = json.dumps(capabilities or [])
        now = time.time()
        conn = ActionScheduler._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO node_registry (
                    node_id, node_name, node_type, cpu_logical, ram_gb,
                    gpu_info, capabilities, status, last_heartbeat
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'alive', ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    node_name = excluded.node_name,
                    node_type = excluded.node_type,
                    cpu_logical = excluded.cpu_logical,
                    ram_gb = excluded.ram_gb,
                    gpu_info = excluded.gpu_info,
                    capabilities = excluded.capabilities,
                    status = 'alive',
                    last_heartbeat = excluded.last_heartbeat
                """,
                (
                    node_id,
                    node_name,
                    node_type,
                    cpu_logical,
                    ram_gb,
                    gpu_info,
                    capabilities_json,
                    now,
                ),
            )
            conn.commit()
            log_event("node_manager", f"Registered node: {node_name} [{node_id}] ({node_type})")
        finally:
            conn.close()

    @classmethod
    def update_heartbeat(
        cls,
        node_id: str,
        system_cpu_pct: float,
        system_ram_pct: float,
        active_tasks: int,
        status: str = "alive",
    ) -> bool:
        """Update node heartbeat and current utilization metrics."""
        now = time.time()
        conn = ActionScheduler._get_conn()
        try:
            # Check if the node is registered first
            exists = conn.execute(
                "SELECT 1 FROM node_registry WHERE node_id = ?", (node_id,)
            ).fetchone()
            if not exists:
                return False

            conn.execute(
                """
                UPDATE node_registry
                SET system_cpu_pct = ?,
                    system_ram_pct = ?,
                    active_tasks = ?,
                    status = ?,
                    last_heartbeat = ?
                WHERE node_id = ?
                """,
                (system_cpu_pct, system_ram_pct, active_tasks, status, now, node_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    @classmethod
    def get_nodes(cls) -> List[Dict[str, Any]]:
        """Retrieve all nodes from the registry."""
        conn = ActionScheduler._get_conn()
        try:
            rows = conn.execute("SELECT * FROM node_registry").fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["capabilities"] = json.loads(d["capabilities"])
                result.append(d)
            return result
        finally:
            conn.close()

    @classmethod
    def get_active_nodes(cls) -> List[Dict[str, Any]]:
        """Retrieve all nodes that are currently 'alive' or 'degraded'."""
        conn = ActionScheduler._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM node_registry WHERE status IN ('alive', 'degraded')"
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["capabilities"] = json.loads(d["capabilities"])
                result.append(d)
            return result
        finally:
            conn.close()

    @classmethod
    def sweep_nodes(cls, timeout_secs: float = 60.0) -> int:
        """Sweep the registry and mark nodes as 'offline' if heartbeat is stale."""
        now = time.time()
        threshold = now - timeout_secs
        conn = ActionScheduler._get_conn()
        try:
            stale_nodes = conn.execute(
                "SELECT node_id, node_name FROM node_registry WHERE status != 'offline' AND last_heartbeat < ?",
                (threshold,),
            ).fetchall()
            swept_count = 0
            for node in stale_nodes:
                conn.execute(
                    "UPDATE node_registry SET status = 'offline' WHERE node_id = ?",
                    (node["node_id"],),
                )
                cls.deregister_connection(node["node_id"])
                log_event("node_manager", f"Node marked OFFLINE (stale heartbeat): {node['node_name']} [{node['node_id']}]")
                swept_count += 1
            if swept_count > 0:
                conn.commit()
            return swept_count
        finally:
            conn.close()
