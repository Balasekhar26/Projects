import psutil
from typing import Dict, Any
from backend.core.governor.base import BaseGovernor, GovernorAction

class CpuGovernor(BaseGovernor):
    """
    Monitors CPU utilization and compression states to guarantee OS and
    foreground application CPU headroom.
    """
    
    def get_metrics(self) -> Dict[str, Any]:
        # non-blocking CPU check
        cpu_percent = psutil.cpu_percent(interval=None)
        # In case interval=None returns 0.0 on the very first call, fallback
        if cpu_percent == 0.0:
            cpu_percent = psutil.cpu_percent(interval=0.1)
        return {"cpu_percent": cpu_percent}

    def assess(self) -> Dict[str, Any]:
        metrics = self.get_metrics()
        cpu_percent = metrics["cpu_percent"]
        available_capacity = max(0.0, 100.0 - cpu_percent)
        
        # Enforce OS / foreground application headroom policy (guarantee at least 50% CPU remains available)
        if cpu_percent > 90.0:
            action = GovernorAction.PAUSE
            risk_score = 0.95
            priority = 9
            reason = f"CPU usage is critical at {cpu_percent}%. OS headroom exhausted."
        elif cpu_percent > 80.0:
            action = GovernorAction.PAUSE
            risk_score = 0.85
            priority = 8
            reason = f"CPU usage is high at {cpu_percent}%. Violating CPU safety threshold."
        elif cpu_percent > 50.0:
            # Recommending ECO to scale back usage and preserve 50% headroom
            action = GovernorAction.ECO
            risk_score = 0.50
            priority = 5
            reason = f"CPU usage is at {cpu_percent}%. Preserving 50% system headroom."
        else:
            action = GovernorAction.NONE
            risk_score = 0.10
            priority = 1
            reason = f"CPU usage is nominal at {cpu_percent}%."

        return {
            "available_capacity": available_capacity,
            "risk_score": risk_score,
            "priority": priority,
            "recommended_action": action,
            "reason": reason,
            "metrics": metrics
        }
