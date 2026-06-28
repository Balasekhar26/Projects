import threading
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List

class GovernorAction(str, Enum):
    NONE = "none"
    ECO = "eco"
    PAUSE = "pause"
    SHUTDOWN = "shutdown"

class BaseGovernor(ABC):
    """
    Abstract Base Governor that monitors a specific hardware or system dimension.
    Each governor subclass must publish metrics, available capacity, risk score,
    priority, confidence, and recommended actions.
    """
    
    def __init__(self, priority: int):
        self.priority = priority
        self.confidence = 1.0
        self._history: Dict[str, List[float]] = {}
        self._history_lock = threading.Lock()

    def add_history_value(self, key: str, val: float, max_len: int = 30) -> float:
        """
        Helper method to add a value to a history buffer and return its average.
        Enables sensor smoothing over a configurable sliding window.
        """
        with self._history_lock:
            if key not in self._history:
                self._history[key] = []
            self._history[key].append(val)
            if len(self._history[key]) > max_len:
                self._history[key].pop(0)
            return sum(self._history[key]) / len(self._history[key])

    @abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """
        Gathers and returns real-time metrics for this specific resource dimension.
        """
        pass

    @abstractmethod
    def assess(self) -> Dict[str, Any]:
        """
        Evaluates the current state of this resource dimension.
        
        Returns:
            Dict[str, Any] containing:
            - available_capacity: float (0.0 to 100.0 representing % headroom)
            - risk_score: float (0.0 to 1.0 representing safety risk)
            - priority: int (Static priority ranking)
            - confidence: float (0.0 to 1.0 sensor confidence rating)
            - recommended_action: GovernorAction (NONE, ECO, PAUSE, SHUTDOWN)
            - reason: str (a short summary explaining the recommendation)
        """
        pass
