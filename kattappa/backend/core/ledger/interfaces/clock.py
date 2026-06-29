from abc import ABC, abstractmethod


class Clock(ABC):
    @abstractmethod
    def now_utc(self) -> float:
        """Returns the current UTC timestamp as a float."""
        pass


class SystemClock(Clock):
    import time

    def now_utc(self) -> float:
        import time

        return time.time()


class TestClock(Clock):
    __test__ = False

    def __init__(self, initial_time: float = 0.0):
        self._current_time = initial_time

    def now_utc(self) -> float:
        return self._current_time

    def advance(self, seconds: float) -> None:
        self._current_time += seconds
