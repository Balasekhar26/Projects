from abc import ABC, abstractmethod
import uuid


class IdGenerator(ABC):
    @abstractmethod
    def generate_id(self) -> str:
        """Generates a unique identifier as a string."""
        pass


class UUIDGenerator(IdGenerator):
    def generate_id(self) -> str:
        return str(uuid.uuid4())


class SequentialGenerator(IdGenerator):
    def __init__(self, prefix: str = "evt-", start: int = 1):
        self._current = start
        self._prefix = prefix

    def generate_id(self) -> str:
        val = f"{self._prefix}{self._current}"
        self._current += 1
        return val
