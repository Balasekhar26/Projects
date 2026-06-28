"""Goal Hierarchy — Phase K11.

Supports a unified 5-level goal tracking structure:
Goal (Level 1) → Subgoal (Level 2) → Task (Level 3) → Action (Level 4) → Tool Call (Level 5).
Persisted in the main SQLite database for transaction consistency.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event


class HierarchyLevel(str, Enum):
    GOAL = "GOAL"
    SUBGOAL = "SUBGOAL"
    TASK = "TASK"
    ACTION = "ACTION"
    TOOL_CALL = "TOOL_CALL"


@dataclass
class HierarchyNode:
    id: str
    parent_id: Optional[str]
    level: HierarchyLevel
    title: str
    description: Optional[str]
    status: str
    progress: float  # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "level": self.level.value,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "progress": self.progress,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class GoalHierarchy:
    """Interface to read and write the 5-level goal/task/action hierarchy."""

    _lock = threading.Lock()

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "goal_hierarchy.db"
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        cls._ensure_schema(conn)
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goal_hierarchy (
                id TEXT PRIMARY KEY,
                parent_id TEXT,
                level TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'PROPOSED',
                progress REAL NOT NULL DEFAULT 0.0,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                completed_at REAL
            )
            """
        )
        conn.commit()

    @classmethod
    def add_node(
        self,
        node_id: str,
        parent_id: Optional[str],
        level: HierarchyLevel,
        title: str,
        description: Optional[str] = None,
        status: str = "PROPOSED",
        progress: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HierarchyNode:
        """Add a new node to the hierarchy."""
        meta = metadata or {}
        now = time.time()
        node = HierarchyNode(
            id=node_id,
            parent_id=parent_id,
            level=level,
            title=title,
            description=description,
            status=status,
            progress=progress,
            metadata=meta,
            created_at=now,
        )

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO goal_hierarchy (id, parent_id, level, title, description, status, progress, metadata, created_at, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node.id,
                        node.parent_id,
                        node.level.value,
                        node.title,
                        node.description,
                        node.status,
                        node.progress,
                        json.dumps(node.metadata),
                        node.created_at,
                        node.completed_at,
                    ),
                )
                conn.commit()
                log_event("goal_hierarchy_add", f"Added {level.value}: {title} (id={node.id})")
            finally:
                conn.close()
        return node

    @classmethod
    def update_node(
        self,
        node_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
    ) -> bool:
        """Update node status and/or progress, propagating progress up the tree."""
        with self._lock:
            conn = self._get_conn()
            try:
                # 1. Fetch current node
                row = conn.execute("SELECT * FROM goal_hierarchy WHERE id = ?", (node_id,)).fetchone()
                if not row:
                    return False

                updates = []
                params: list[Any] = []
                if status is not None:
                    updates.append("status = ?")
                    params.append(status)
                    if status in ("COMPLETED", "DONE"):
                        updates.append("completed_at = ?")
                        params.append(time.time())
                if progress is not None:
                    updates.append("progress = ?")
                    params.append(progress)

                if not updates:
                    return True

                params.append(node_id)
                conn.execute(
                    f"UPDATE goal_hierarchy SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
                conn.commit()

                # 2. Propagate progress upward to parent
                parent_id = row["parent_id"]
                if parent_id:
                    self._propagate_progress_up(conn, parent_id)

                log_event("goal_hierarchy_update", f"Updated node={node_id} status={status} progress={progress}")
                return True
            finally:
                conn.close()

    @classmethod
    def _propagate_progress_up(cls, conn: sqlite3.Connection, parent_id: str) -> None:
        """Recursively calculate parent progress as average of children progress."""
        children = conn.execute("SELECT progress, status FROM goal_hierarchy WHERE parent_id = ?", (parent_id,)).fetchall()
        if not children:
            return

        total_progress = sum(row["progress"] for row in children)
        avg_progress = total_progress / len(children)

        # If all children are completed, complete the parent
        all_completed = all(row["status"] in ("COMPLETED", "DONE", "CANCELLED") for row in children)
        status_update = "COMPLETED" if all_completed else "ACTIVE"

        conn.execute(
            "UPDATE goal_hierarchy SET progress = ?, status = ?, completed_at = ? WHERE id = ?",
            (
                avg_progress,
                status_update,
                time.time() if all_completed else None,
                parent_id,
            ),
        )
        conn.commit()

        # Bubble up
        parent_row = conn.execute("SELECT parent_id FROM goal_hierarchy WHERE id = ?", (parent_id,)).fetchone()
        if parent_row and parent_row["parent_id"]:
            cls._propagate_progress_up(conn, parent_row["parent_id"])

    @classmethod
    def get_node(self, node_id: str) -> Optional[HierarchyNode]:
        """Retrieve a specific hierarchy node."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT * FROM goal_hierarchy WHERE id = ?", (node_id,)).fetchone()
                if row:
                    return HierarchyNode(
                        id=row["id"],
                        parent_id=row["parent_id"],
                        level=HierarchyLevel(row["level"]),
                        title=row["title"],
                        description=row["description"],
                        status=row["status"],
                        progress=row["progress"],
                        metadata=json.loads(row["metadata"]),
                        created_at=row["created_at"],
                        completed_at=row["completed_at"],
                    )
                return None
            finally:
                conn.close()

    @classmethod
    def get_children(self, parent_id: str) -> List[HierarchyNode]:
        """Get all children nodes for a parent."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT * FROM goal_hierarchy WHERE parent_id = ?", (parent_id,)).fetchall()
                return [
                    HierarchyNode(
                        id=row["id"],
                        parent_id=row["parent_id"],
                        level=HierarchyLevel(row["level"]),
                        title=row["title"],
                        description=row["description"],
                        status=row["status"],
                        progress=row["progress"],
                        metadata=json.loads(row["metadata"]),
                        created_at=row["created_at"],
                        completed_at=row["completed_at"],
                    )
                    for row in rows
                ]
            finally:
                conn.close()

    @classmethod
    def get_active_tree(self) -> Dict[str, Any]:
        """Build and return the entire active (non-completed) 5-level hierarchy tree."""
        with self._lock:
            conn = self._get_conn()
            try:
                # Fetch all non-completed nodes
                rows = conn.execute(
                    "SELECT * FROM goal_hierarchy WHERE status NOT IN ('COMPLETED', 'CANCELLED', 'FAILED')"
                ).fetchall()

                nodes_by_id = {}
                roots = []

                for row in rows:
                    node_dict = {
                        "id": row["id"],
                        "parent_id": row["parent_id"],
                        "level": row["level"],
                        "title": row["title"],
                        "description": row["description"],
                        "status": row["status"],
                        "progress": row["progress"],
                        "metadata": json.loads(row["metadata"]),
                        "children": [],
                    }
                    nodes_by_id[row["id"]] = node_dict

                for nid, node in nodes_by_id.items():
                    pid = node["parent_id"]
                    if pid and pid in nodes_by_id:
                        nodes_by_id[pid]["children"].append(node)
                    else:
                        # Top-level goal
                        if node["level"] == "GOAL":
                            roots.append(node)

                return {"roots": roots}
            finally:
                conn.close()

    @classmethod
    def reset(cls) -> None:
        """Reset the goal hierarchy table (useful for tests)."""
        with cls._lock:
            conn = cls._get_conn()
            try:
                conn.execute("DROP TABLE IF EXISTS goal_hierarchy")
                conn.commit()
            finally:
                conn.close()
