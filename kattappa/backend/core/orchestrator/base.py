from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from backend.core.orchestrator.context import SharedContext

class Task:
    def __init__(
        self,
        task_id: str | None,
        agent_name: str,
        action: str,
        params: dict[str, Any],
        dependencies: list[str] | None = None,
        priority: float = 0.5,
    ):
        self.task_id = task_id or str(uuid.uuid4())
        self.agent_name = agent_name
        self.action = action
        self.params = params
        self.dependencies = dependencies or []
        self.status = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
        self.retry_count = 0
        self.error: str | None = None
        self.output: Any = None
        self.priority = priority

class TaskResult:
    def __init__(self, success: bool, output: Any = None, error: str | None = None):
        self.success = success
        self.output = output
        self.error = error

class BaseAgent(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def initialize(self) -> None:
        pass

    @abstractmethod
    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        pass

    @abstractmethod
    def terminate(self, task_id: str) -> None:
        pass
