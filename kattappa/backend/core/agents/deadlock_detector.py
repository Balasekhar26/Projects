"""Deadlock Detector — Wait-For Graph (Program 16.0).

Maintains a directed wait-for graph among running agent tasks.
An edge A → B means "task A is waiting for task B to complete."
A cycle in this graph means deadlock.

Usage:
    detector = DeadlockDetector()
    detector.register_wait("task-A", "task-B")  # A waits on B
    detector.register_wait("task-B", "task-A")  # B also waits on A
    cycles = detector.detect_and_report()       # returns [["task-A", "task-B"]]
    detector.release("task-B")                  # B completed, remove its out-edges
"""
from __future__ import annotations

import threading
from typing import Dict, List, Optional, Set


class DeadlockDetector:
    """Thread-safe directed wait-for graph with DFS cycle detection."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # waiter_id -> set of task_ids it is waiting for
        self._wait_for: Dict[str, Set[str]] = {}

    def register_wait(self, waiter_id: str, waiting_for_id: str) -> None:
        """Record that *waiter_id* is blocked pending completion of *waiting_for_id*."""
        with self._lock:
            if waiter_id not in self._wait_for:
                self._wait_for[waiter_id] = set()
            self._wait_for[waiter_id].add(waiting_for_id)

    def release(self, completed_id: str) -> None:
        """Remove all out-edges for a task that has finished (no longer blocking anyone)."""
        with self._lock:
            self._wait_for.pop(completed_id, None)
            # Also remove this node from every other task's wait set
            for waiters in self._wait_for.values():
                waiters.discard(completed_id)

    def has_cycle(self) -> bool:
        """Return True if any cycle exists in the current wait-for graph."""
        return bool(self.detect_and_report())

    def detect_and_report(self) -> List[List[str]]:
        """Return a list of detected cycles. Each cycle is an ordered list of task IDs."""
        with self._lock:
            graph = {k: set(v) for k, v in self._wait_for.items()}

        cycles: List[List[str]] = []
        visited: Set[str] = set()
        rec_stack: List[str] = []

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.append(node)

            for neighbour in graph.get(node, set()):
                if neighbour not in visited:
                    if dfs(neighbour):
                        return True
                elif neighbour in rec_stack:
                    # Found a cycle — extract the cycle path
                    cycle_start = rec_stack.index(neighbour)
                    cycles.append(list(rec_stack[cycle_start:]))
                    return True

            rec_stack.pop()
            return False

        for node in list(graph.keys()):
            if node not in visited:
                dfs(node)

        return cycles

    def snapshot(self) -> Dict[str, List[str]]:
        """Return a copy of the current wait-for graph for diagnostics."""
        with self._lock:
            return {k: sorted(v) for k, v in self._wait_for.items()}
