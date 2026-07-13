from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class PlannerInterface(ABC):
    """Abstract interface defining required persistent planning operations."""

    @abstractmethod
    def create_plan(
        self,
        goal: Any,
        world_state: Dict[str, Any],
        constraints: Dict[str, Any]
    ) -> Any:
        """Decomposes a goal into a planning DAG execution schema."""
        pass

    @abstractmethod
    def execute_step(
        self,
        step_id: str,
        current_state: Dict[str, Any]
    ) -> Any:
        """Executes a single step of the plan, returning progress indicators."""
        pass

    @abstractmethod
    def checkpoint(self) -> bytes:
        """Serializes current planning stack state to compressed binary logs."""
        pass

    @abstractmethod
    def restore(self, checkpoint: bytes) -> None:
        """Restores planning state from serialized binary checkpoints."""
        pass

    @abstractmethod
    def replan(
        self,
        failed_step_id: str,
        current_state: Dict[str, Any]
    ) -> Any:
        """Computes a fallback or recovery plan starting from the failure node state."""
        pass
