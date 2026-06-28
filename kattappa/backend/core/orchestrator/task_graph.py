from __future__ import annotations
from typing import Dict, List, Set, Any
from backend.core.orchestrator.base import Task

class TaskGraph:
    def __init__(self):
        self.tasks: dict[str, Task] = {}
        # child_id -> list of parent_ids it depends on
        self.dependencies: dict[str, list[str]] = {}

    def add_task(self, task: Task) -> None:
        if task.task_id in self.tasks:
            raise ValueError(f"Task with ID {task.task_id} is already in the graph")
        self.tasks[task.task_id] = task
        self.dependencies[task.task_id] = list(task.dependencies)
        self.verify_no_cycles()

    def add_dependency(self, child_id: str, parent_id: str) -> None:
        if child_id not in self.tasks or parent_id not in self.tasks:
            raise ValueError("Both tasks must exist in the graph")
        if parent_id not in self.dependencies[child_id]:
            self.dependencies[child_id].append(parent_id)
            self.tasks[child_id].dependencies.append(parent_id)
        self.verify_no_cycles()

    def verify_no_cycles(self) -> None:
        visited: dict[str, int] = {}  # 0 = visiting, 1 = visited

        def dfs(node_id: str) -> bool:
            visited[node_id] = 0
            for parent_id in self.dependencies.get(node_id, []):
                state = visited.get(parent_id)
                if state == 0:
                    return True  # Cycle detected
                if state is None:
                    if dfs(parent_id):
                        return True
            visited[node_id] = 1
            return False

        for node_id in self.tasks:
            if node_id not in visited:
                if dfs(node_id):
                    raise ValueError("Circular dependency detected in TaskGraph")

    def get_ready_tasks(self) -> list[Task]:
        """Return tasks that are PENDING and all their dependencies are COMPLETED."""
        ready = []
        for task_id, task in self.tasks.items():
            if task.status != "PENDING":
                continue
            parents_completed = True
            for parent_id in self.dependencies.get(task_id, []):
                parent = self.tasks.get(parent_id)
                if parent is None or parent.status != "COMPLETED":
                    parents_completed = False
                    break
            if parents_completed:
                ready.append(task)
        return ready

    def complete_task(self, task_id: str, output: Any = None) -> None:
        if task_id in self.tasks:
            self.tasks[task_id].status = "COMPLETED"
            self.tasks[task_id].output = output

    def fail_task(self, task_id: str, error: str) -> None:
        if task_id in self.tasks:
            self.tasks[task_id].status = "FAILED"
            self.tasks[task_id].error = error

    def cancel_task(self, task_id: str) -> None:
        if task_id in self.tasks:
            self.tasks[task_id].status = "CANCELLED"

    def is_finished(self) -> bool:
        if not self.tasks:
            return True
        return all(t.status in ("COMPLETED", "FAILED", "CANCELLED") for t in self.tasks.values())

    def has_failures(self) -> bool:
        return any(t.status == "FAILED" for t in self.tasks.values())
