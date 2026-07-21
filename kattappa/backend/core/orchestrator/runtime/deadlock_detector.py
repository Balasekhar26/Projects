"""Deadlock Detector — Wait-For Graph (Program 16.0) — relocated to orchestrator/runtime/.

Maintains a directed wait-for graph among running agent tasks.
An edge A → B means "task A is waiting for task B to complete."
A cycle in this graph means deadlock.
"""
from __future__ import annotations

import threading
from typing import Dict, List, Set


class DeadlockDetector:
    """Thread-safe directed wait-for graph with DFS cycle detection."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wait_for: Dict[str, Set[str]] = {}

    def register_wait(self, waiter_id: str, waiting_for_id: str) -> None:
        with self._lock:
            if waiter_id not in self._wait_for:
                self._wait_for[waiter_id] = set()
            self._wait_for[waiter_id].add(waiting_for_id)

    def release(self, completed_id: str) -> None:
        with self._lock:
            self._wait_for.pop(completed_id, None)
            for waiters in self._wait_for.values():
                waiters.discard(completed_id)

    def has_cycle(self) -> bool:
        return bool(self.detect_and_report())

    def detect_and_report(self) -> List[List[str]]:
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
        with self._lock:
            return {k: sorted(v) for k, v in self._wait_for.items()}
