"""Execution Events and Telemetry EventBus (Program 5G-6).

Defines telemetry events and the in-memory pub-sub dispatcher EventBus.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional



@dataclass
class ExecutionEvent:
    """Base event representation for execution telemetry updates."""
    event_type: str
    session_id: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskStartedEvent(ExecutionEvent):
    node_id: str = ""

    def __init__(self, session_id: str, node_id: str) -> None:
        super().__init__("TaskStarted", session_id)
        self.node_id = node_id


@dataclass
class TaskCompletedEvent(ExecutionEvent):
    node_id: str = ""

    def __init__(self, session_id: str, node_id: str) -> None:
        super().__init__("TaskCompleted", session_id)
        self.node_id = node_id


@dataclass
class TaskFailedEvent(ExecutionEvent):
    node_id: str = ""
    error_message: str = ""

    def __init__(self, session_id: str, node_id: str, error_message: str) -> None:
        super().__init__("TaskFailed", session_id)
        self.node_id = node_id
        self.error_message = error_message



@dataclass
class ToolStartedEvent(ExecutionEvent):
    tool_name: str = ""

    def __init__(self, session_id: str, tool_name: str) -> None:
        super().__init__("ToolStarted", session_id)
        self.tool_name = tool_name


@dataclass
class ToolCompletedEvent(ExecutionEvent):
    tool_name: str = ""
    result: Any = None

    def __init__(self, session_id: str, tool_name: str, result: Any) -> None:
        super().__init__("ToolCompleted", session_id)
        self.tool_name = tool_name
        self.result = result


@dataclass
class ToolFailedEvent(ExecutionEvent):
    tool_name: str = ""
    error_message: str = ""

    def __init__(self, session_id: str, tool_name: str, error_message: str) -> None:
        super().__init__("ToolFailed", session_id)
        self.tool_name = tool_name
        self.error_message = error_message


@dataclass
class ToolCancelledEvent(ExecutionEvent):
    tool_name: str = ""

    def __init__(self, session_id: str, tool_name: str) -> None:
        super().__init__("ToolCancelled", session_id)
        self.tool_name = tool_name


class EventBus:
    """Thread-safe in-memory pub-sub dispatcher for execution events."""

    _instance: Optional[EventBus] = None

    def __init__(self) -> None:
        self.subscribers: List[Callable[[ExecutionEvent], None]] = []

    @classmethod
    def get_instance(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def subscribe(self, subscriber: Callable[[ExecutionEvent], None]) -> None:
        self.subscribers.append(subscriber)

    def publish(self, event: ExecutionEvent) -> None:
        for sub in self.subscribers:
            try:
                sub(event)
            except Exception:
                # Suppress subscriber callbacks error to prevent breaking execution
                pass
