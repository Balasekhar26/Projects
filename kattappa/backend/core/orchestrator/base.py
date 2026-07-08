from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from backend.core.orchestrator.context import SharedContext

# Maximum allowed delegation nesting depth (Executive → Worker = depth 1,
# Worker spawning a sub-task = depth 2, which is the hard ceiling).
MAX_AGENT_DEPTH: int = 2

# Spawn quota limits — breadth controls to prevent fan-out explosions.
MAX_CHILDREN_PER_AGENT: int = 5   # single agent may spawn at most 5 direct children
MAX_TOTAL_AGENTS: int = 20        # total active workers across the entire graph


class DelegationDepthExceeded(Exception):
    """Raised when a task would exceed the maximum allowed agent delegation depth."""
    def __init__(self, depth: int) -> None:
        super().__init__(
            f"Delegation depth {depth} exceeds maximum allowed depth {MAX_AGENT_DEPTH}"
        )


class SpawnQuotaExceeded(Exception):
    """Raised when spawning a new agent task would exceed a quota limit."""
    def __init__(self, reason: str) -> None:
        super().__init__(f"Spawn quota exceeded: {reason}")


class Task:
    def __init__(
        self,
        task_id: str | None,
        agent_name: str,
        action: str,
        params: dict[str, Any],
        dependencies: list[str] | None = None,
        priority: float = 0.5,
        delegation_depth: int = 0,
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
        self.delegation_depth = delegation_depth


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
