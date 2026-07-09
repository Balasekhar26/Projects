"""Unified Execution Context (Program 33.0).

Defines the centralized ExecutionContext dataclass carrying all cognitive states
(goals, constraints, memories, beliefs, budgets, safety, traces) and
the thread-local CognitiveContextManager.
"""
from __future__ import annotations

import copy
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExecutionContext:
    """The central state model representing the runtime context of Kattappa."""

    goals: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    memory_references: List[str] = field(default_factory=list)
    beliefs: Dict[str, Any] = field(default_factory=dict)
    budget: Dict[str, Any] = field(default_factory=dict)
    permissions: Dict[str, Any] = field(default_factory=dict)
    active_spans: List[str] = field(default_factory=list)
    safety_flags: Dict[str, Any] = field(default_factory=dict)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    trace_identifiers: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes context parameters to standard dictionary."""
        return asdict(self)

    def clone(self) -> ExecutionContext:
        """Returns a deep copy of the execution context parameters."""
        return copy.deepcopy(self)


class CognitiveContextManager:
    """Thread-safe context manager tracking active ExecutionContext variables."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls) -> CognitiveContextManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_manager()
            return cls._instance

    def _init_manager(self) -> None:
        self._local = threading.local()

    def clear(self) -> None:
        """Resets the context manager thread local attributes."""
        self._local.__dict__.clear()

    def get_current(self) -> ExecutionContext:
        """Returns the active context or instantiates a fresh context."""
        if not hasattr(self._local, "context") or self._local.context is None:
            self._local.context = ExecutionContext()
        return self._local.context

    def set_current(self, context: ExecutionContext) -> None:
        """Assigns the active execution context for the current thread."""
        if not isinstance(context, ExecutionContext):
            raise TypeError("Value must be an instance of ExecutionContext")
        self._local.context = context

    def clone_context(self) -> ExecutionContext:
        """Returns a cloned copy of the active execution context."""
        return self.get_current().clone()
