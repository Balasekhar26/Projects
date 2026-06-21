"""Goal Manager (Phase 4).

Turns a single request/response into tracked goals with subgoals, dependencies,
progress and completion. Deterministic and persistent; it tracks state and never
executes anything.

    Build DEWS
      ├─ Hardware
      ├─ Firmware   (depends_on: Hardware)
      ├─ RF Testing (depends_on: Firmware)
      └─ Deployment (depends_on: RF Testing)
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _path() -> Path:
    return runtime_data_root() / "backend" / "data" / "goals.json"


class GoalStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    DONE = "done"
    ABANDONED = "abandoned"


class GoalManager:
    _lock = threading.RLock()

    # -- persistence -------------------------------------------------------
    @classmethod
    def _load(cls) -> dict[str, Any]:
        try:
            p = _path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"goals": {}}

    @classmethod
    def _save(cls, data: dict[str, Any]) -> None:
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    # -- creation ----------------------------------------------------------
    @classmethod
    def add_goal(
        cls,
        title: str,
        parent_id: str | None = None,
        depends_on: list[str] | None = None,
    ) -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("Goal title cannot be empty")
        depends_on = list(depends_on or [])
        with cls._lock:
            data = cls._load()
            goals = data.setdefault("goals", {})
            if parent_id is not None and parent_id not in goals:
                raise ValueError(f"Parent goal {parent_id!r} does not exist")
            for dep in depends_on:
                if dep not in goals:
                    raise ValueError(f"Dependency {dep!r} does not exist")
            goal = {
                "id": uuid.uuid4().hex[:12],
                "title": title,
                "status": GoalStatus.PENDING.value,
                "parent_id": parent_id,
                "depends_on": depends_on,
                "created_at": time.time(),
                "updated_at": time.time(),
            }
            # Adding can't create a cycle (new node has no incoming edges yet),
            # but guard anyway in case of future edits.
            goals[goal["id"]] = goal
            if cls._has_cycle(goals):
                del goals[goal["id"]]
                raise ValueError("Dependency cycle detected")
            cls._save(data)
            return goal

    # -- transitions -------------------------------------------------------
    @classmethod
    def _set_status(cls, goal_id: str, status: GoalStatus) -> dict[str, Any]:
        with cls._lock:
            data = cls._load()
            goals = data.get("goals", {})
            goal = goals.get(goal_id)
            if goal is None:
                raise KeyError(f"No goal {goal_id!r}")
            goal["status"] = status.value
            goal["updated_at"] = time.time()
            cls._save(data)
            return goal

    @classmethod
    def start(cls, goal_id: str) -> dict[str, Any]:
        with cls._lock:
            data = cls._load()
            goals = data.get("goals", {})
            goal = goals.get(goal_id)
            if goal is None:
                raise KeyError(f"No goal {goal_id!r}")
            unmet = [d for d in goal.get("depends_on", [])
                     if goals.get(d, {}).get("status") != GoalStatus.DONE.value]
            goal["status"] = (GoalStatus.BLOCKED.value if unmet else GoalStatus.ACTIVE.value)
            goal["updated_at"] = time.time()
            cls._save(data)
            return goal

    @classmethod
    def complete(cls, goal_id: str) -> dict[str, Any]:
        return cls._set_status(goal_id, GoalStatus.DONE)

    @classmethod
    def abandon(cls, goal_id: str) -> dict[str, Any]:
        return cls._set_status(goal_id, GoalStatus.ABANDONED)

    # -- queries -----------------------------------------------------------
    @classmethod
    def get(cls, goal_id: str) -> dict[str, Any] | None:
        return cls._load().get("goals", {}).get(goal_id)

    @classmethod
    def list_goals(cls) -> list[dict[str, Any]]:
        return list(cls._load().get("goals", {}).values())

    @classmethod
    def subgoals(cls, parent_id: str) -> list[dict[str, Any]]:
        return [g for g in cls.list_goals() if g.get("parent_id") == parent_id]

    @classmethod
    def ready_goals(cls) -> list[dict[str, Any]]:
        """Pending goals whose dependencies are all done."""
        goals = cls._load().get("goals", {})
        ready = []
        for g in goals.values():
            if g.get("status") != GoalStatus.PENDING.value:
                continue
            if all(goals.get(d, {}).get("status") == GoalStatus.DONE.value
                   for d in g.get("depends_on", [])):
                ready.append(g)
        return ready

    @classmethod
    def progress(cls, goal_id: str) -> float:
        goals = cls._load().get("goals", {})
        return cls._progress(goal_id, goals)

    @classmethod
    def _progress(cls, goal_id: str, goals: dict[str, Any]) -> float:
        children = [g for g in goals.values() if g.get("parent_id") == goal_id]
        if not children:
            status = goals.get(goal_id, {}).get("status")
            return 1.0 if status == GoalStatus.DONE.value else 0.0
        done = sum(1 for c in children
                   if c.get("status") == GoalStatus.DONE.value
                   or cls._progress(c["id"], goals) == 1.0)
        return round(done / len(children), 4)

    @staticmethod
    def _has_cycle(goals: dict[str, Any]) -> bool:
        WHITE, GREY, BLACK = 0, 1, 2
        color = {gid: WHITE for gid in goals}

        def visit(node: str) -> bool:
            color[node] = GREY
            for dep in goals.get(node, {}).get("depends_on", []):
                if dep not in color:
                    continue
                if color[dep] == GREY:
                    return True
                if color[dep] == WHITE and visit(dep):
                    return True
            color[node] = BLACK
            return False

        return any(color[g] == WHITE and visit(g) for g in goals)

    @classmethod
    def status(cls) -> dict[str, Any]:
        goals = cls.list_goals()
        by_status: dict[str, int] = {s.value: 0 for s in GoalStatus}
        for g in goals:
            by_status[g.get("status", "pending")] = by_status.get(g.get("status", "pending"), 0) + 1
        roots = [g for g in goals if not g.get("parent_id")]
        return {
            "total_goals": len(goals),
            "by_status": by_status,
            "roots": [{"id": g["id"], "title": g["title"],
                       "progress": cls.progress(g["id"])} for g in roots],
            "ready": [g["id"] for g in cls.ready_goals()],
        }

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._save({"goals": {}})
