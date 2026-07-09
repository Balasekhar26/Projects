"""Context Lifecycle Hooks (Program 33.0).

Coordinates events and triggers executing callbacks when the centralized
execution context transitions, goals start, actions dispatch, or errors raise.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional

from backend.core.context.cognitive_context import ExecutionContext

logger = logging.getLogger(__name__)


class LifecycleHookManager:
    """Manages event callback registries and dispatches triggers on transitions."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls) -> LifecycleHookManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_hooks()
            return cls._instance

    def _init_hooks(self) -> None:
        self.listeners: Dict[str, List[Callable[..., Any]]] = {
            "on_goal_start": [],
            "on_action_dispatch": [],
            "on_context_change": [],
            "on_error_raised": [],
        }

    def clear_hooks(self) -> None:
        """Clears all registered listener callbacks."""
        for event in self.listeners:
            self.listeners[event].clear()

    def register_hook(self, event_name: str, callback: Callable[..., Any]) -> None:
        """Registers a listener callback for the named transition event."""
        if event_name not in self.listeners:
            raise ValueError(f"Unsupported context lifecycle event: {event_name}")
        self.listeners[event_name].append(callback)

    # ── Fire Triggers ─────────────────────────────────────────────────────────

    def fire_goal_start(self, context: ExecutionContext, goal_id: str) -> None:
        """Fires the on_goal_start event callbacks."""
        for callback in self.listeners["on_goal_start"]:
            try:
                callback(context, goal_id)
            except Exception as e:
                logger.error(f"Error executing on_goal_start callback: {e}")

    def fire_action_dispatch(
        self,
        context: ExecutionContext,
        tool_name: str,
        args: Dict[str, Any],
    ) -> None:
        """Fires the on_action_dispatch event callbacks."""
        for callback in self.listeners["on_action_dispatch"]:
            try:
                callback(context, tool_name, args)
            except Exception as e:
                logger.error(f"Error executing on_action_dispatch callback: {e}")

    def fire_context_change(
        self,
        context: ExecutionContext,
        key: str,
        new_val: Any,
    ) -> None:
        """Fires the on_context_change event callbacks."""
        for callback in self.listeners["on_context_change"]:
            try:
                callback(context, key, new_val)
            except Exception as e:
                logger.error(f"Error executing on_context_change callback: {e}")

    def fire_error_raised(self, context: ExecutionContext, exception: Exception) -> None:
        """Fires the on_error_raised event callbacks."""
        for callback in self.listeners["on_error_raised"]:
            try:
                callback(context, exception)
            except Exception as e:
                logger.error(f"Error executing on_error_raised callback: {e}")
