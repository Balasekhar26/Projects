"""Executive Workspace — Phase K10.5.

Maintains active, transient working registers (scratchpad, reasoning stack,
thought queue, active hypotheses) that act as the CPU registers for Kattappa's
current execution thread.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional


class ExecutiveWorkspace:
    """Thread-safe active register set for high-frequency runtime representations."""

    _instance: Optional[ExecutiveWorkspace] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._lock = threading.Lock()
        self._scratchpad: Dict[str, Any] = {}
        self._reasoning_stack: List[str] = []
        self._thought_queue: List[str] = []
        self._active_hypotheses: List[Dict[str, Any]] = []
        self._registers: Dict[str, Any] = {}
        self._initialized = True

    # -- Scratchpad CRUD --
    def write_scratchpad(self, key: str, value: Any) -> None:
        with self._lock:
            self._scratchpad[key] = value

    def read_scratchpad(self, key: str) -> Any:
        with self._lock:
            return self._scratchpad.get(key)

    def clear_scratchpad(self) -> None:
        with self._lock:
            self._scratchpad.clear()

    # -- Reasoning Stack --
    def push_reasoning(self, step: str) -> None:
        with self._lock:
            self._reasoning_stack.append(step)

    def pop_reasoning(self) -> Optional[str]:
        with self._lock:
            if self._reasoning_stack:
                return self._reasoning_stack.pop()
            return None

    def get_reasoning_stack(self) -> List[str]:
        with self._lock:
            return list(self._reasoning_stack)

    # -- Thought Queue --
    def enqueue_thought(self, thought: str) -> None:
        with self._lock:
            self._thought_queue.append(thought)

    def dequeue_thought(self) -> Optional[str]:
        with self._lock:
            if self._thought_queue:
                return self._thought_queue.pop(0)
            return None

    def get_thought_queue(self) -> List[str]:
        with self._lock:
            return list(self._thought_queue)

    # -- Active Hypotheses --
    def add_hypothesis(self, hypothesis: Dict[str, Any]) -> None:
        with self._lock:
            self._active_hypotheses.append(hypothesis)

    def get_active_hypotheses(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._active_hypotheses)

    def clear_hypotheses(self) -> None:
        with self._lock:
            self._active_hypotheses.clear()

    # -- Key-Value Registers --
    def set_register(self, key: str, value: Any) -> None:
        with self._lock:
            self._registers[key] = value

    def get_register(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._registers.get(key, default)

    def clear_registers(self) -> None:
        with self._lock:
            self._registers.clear()

    def reset_workspace(self) -> None:
        """Reset all workspace registers to empty state."""
        with self._lock:
            self._scratchpad.clear()
            self._reasoning_stack.clear()
            self._thought_queue.clear()
            self._active_hypotheses.clear()
            self._registers.clear()

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "scratchpad": dict(self._scratchpad),
                "reasoning_stack": list(self._reasoning_stack),
                "thought_queue": list(self._thought_queue),
                "active_hypotheses": list(self._active_hypotheses),
                "registers": dict(self._registers),
            }

    def from_dict(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self._scratchpad = dict(data.get("scratchpad", {}))
            self._reasoning_stack = list(data.get("reasoning_stack", []))
            self._thought_queue = list(data.get("thought_queue", []))
            self._active_hypotheses = list(data.get("active_hypotheses", []))
            self._registers = dict(data.get("registers", {}))


# Global Singleton reference
WORKSPACE = ExecutiveWorkspace()
