import psutil
from typing import Dict, Any
from backend.core.governor.base import BaseGovernor, GovernorAction

class CpuGovernor(BaseGovernor):
    """
    Monitors CPU utilization and compression states to guarantee OS and
    foreground application CPU headroom, using sliding window smoothing.
    """
    
    def __init__(self):
        super().__init__(priority=60)

    def get_metrics(self) -> Dict[str, Any]:
        # non-blocking CPU check
        cpu_percent = psutil.cpu_percent(interval=None)
        if cpu_percent == 0.0:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
        # Keep 5s and 30s averages (assuming polled ~1s intervals)
        cpu_5s_avg = self.add_history_value("cpu_5s", cpu_percent, max_len=5)
        cpu_30s_avg = self.add_history_value("cpu_30s", cpu_percent, max_len=30)
        
        return {
            "cpu_percent": cpu_percent,
            "cpu_5s_avg": round(cpu_5s_avg, 1),
            "cpu_30s_avg": round(cpu_30s_avg, 1)
        }

    def assess(self) -> Dict[str, Any]:
        metrics = self.get_metrics()
        
        # Use smoothed 30s average to prevent oscillation in decision making
        cpu_eval = metrics["cpu_30s_avg"]
        available_capacity = max(0.0, 100.0 - cpu_eval)
        
        # Enforce OS / foreground application headroom policy (guarantee at least 50% CPU remains available)
        if cpu_eval > 90.0:
            action = GovernorAction.PAUSE
            risk_score = 0.95
            reason = f"CPU 30s avg usage is critical at {cpu_eval}%. OS headroom exhausted."
        elif cpu_eval > 80.0:
            action = GovernorAction.PAUSE
            risk_score = 0.85
            reason = f"CPU 30s avg usage is high at {cpu_eval}%. Violating CPU safety threshold."
        elif cpu_eval > 50.0:
            action = GovernorAction.ECO
            risk_score = 0.50
            reason = f"CPU 30s avg usage is at {cpu_eval}%. Preserving 50% system headroom."
        else:
            action = GovernorAction.NONE
            risk_score = 0.10
            reason = f"CPU 30s avg usage is nominal at {cpu_eval}%."

        return {
            "available_capacity": available_capacity,
            "risk_score": risk_score,
            "priority": self.priority,
            "confidence": self.confidence,
            "recommended_action": action,
            "reason": reason,
            "metrics": metrics
        }
