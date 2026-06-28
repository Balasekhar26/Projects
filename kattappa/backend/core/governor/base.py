from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any

class GovernorAction(str, Enum):
    NONE = "none"
    ECO = "eco"
    PAUSE = "pause"
    SHUTDOWN = "shutdown"

class BaseGovernor(ABC):
    """
    Abstract Base Governor that monitors a specific hardware or system dimension.
    Each governor subclass must publish metrics, available capacity, risk score,
    priority, and recommended actions.
    """
    
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
            - priority: int (1 to 10, where 10 is critical/urgent)
            - recommended_action: GovernorAction (NONE, ECO, PAUSE, SHUTDOWN)
            - reason: str (a short summary explaining the recommendation)
        """
        pass
