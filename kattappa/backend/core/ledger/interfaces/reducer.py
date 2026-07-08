from abc import ABC, abstractmethod
from typing import Any


class Reducer(ABC):
    @abstractmethod
    def reduce(self, state: Any, event: Any) -> Any:
        """Applies an event to the current state and returns the updated state."""
        pass
