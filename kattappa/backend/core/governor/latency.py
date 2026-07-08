import threading
from typing import Dict, Any, List
from backend.core.governor.base import BaseGovernor, GovernorAction

class LatencyGovernor(BaseGovernor):
    """
    Monitors workflow execution latency and queue lengths to recommend
    fast-path fallback routes and prevent request timeouts.
    """
    
    _lock = threading.Lock()
    _recent_latencies: List[float] = []
    MAX_HISTORY = 20
    
    # Target bounds
    TARGET_LATENCY_MS = 2500.0  # 2.5 seconds max for deep reasoning
    CRITICAL_LATENCY_MS = 5000.0  # 5 seconds is critical

    def __init__(self):
        super().__init__(priority=40)

    @classmethod
    def report_latency(cls, latency_ms: float) -> None:
        """
        Thread-safe method to report a recent execution latency.
        """
        with cls._lock:
            cls._recent_latencies.append(latency_ms)
            if len(cls._recent_latencies) > cls.MAX_HISTORY:
                cls._recent_latencies.pop(0)

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            history = list(self._recent_latencies)
            
        if not history:
            return {"avg_latency_ms": 0.0, "current_queue_len": 0}
            
        avg_latency = sum(history) / len(history)
        return {
            "avg_latency_ms": round(avg_latency, 1),
            "current_queue_len": len(history)
        }

    def assess(self) -> Dict[str, Any]:
        metrics = self.get_metrics()
        avg_ms = metrics["avg_latency_ms"]
        
        if avg_ms == 0.0:
            return {
                "available_capacity": 100.0,
                "risk_score": 0.0,
                "priority": self.priority,
                "confidence": 0.5,  # Moderate confidence when there is no history yet
                "recommended_action": GovernorAction.NONE,
                "reason": "No recent execution latency records found.",
                "metrics": metrics
            }

        available_capacity = max(0.0, (1.0 - avg_ms / self.CRITICAL_LATENCY_MS) * 100.0)

        if avg_ms >= self.CRITICAL_LATENCY_MS:
            action = GovernorAction.PAUSE
            risk_score = 0.90
            reason = f"Average response latency is critical at {avg_ms:.1f}ms (threshold: {self.CRITICAL_LATENCY_MS:.0f}ms). Recommend fast-path fallback."
        elif avg_ms >= self.TARGET_LATENCY_MS:
            action = GovernorAction.ECO
            risk_score = 0.60
            reason = f"Average response latency is elevated at {avg_ms:.1f}ms (target: {self.TARGET_LATENCY_MS:.0f}ms)."
        else:
            action = GovernorAction.NONE
            risk_score = 0.10
            reason = f"Average response latency is nominal at {avg_ms:.1f}ms."

        return {
            "available_capacity": available_capacity,
            "risk_score": risk_score,
            "priority": self.priority,
            "confidence": self.confidence,
            "recommended_action": action,
            "reason": reason,
            "metrics": metrics
        }
