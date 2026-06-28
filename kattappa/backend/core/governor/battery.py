import psutil
from typing import Dict, Any
from backend.core.governor.base import BaseGovernor, GovernorAction

class BatteryGovernor(BaseGovernor):
    """
    Monitors battery level and power plug status to prevent device
    drainage and protect un-saved training state during low power states.
    """
    
    def get_metrics(self) -> Dict[str, Any]:
        metrics = {
            "has_battery": False,
            "percent": 100.0,
            "power_plugged": True
        }
        
        try:
            bat = psutil.sensors_battery()
            if bat is not None:
                metrics["has_battery"] = True
                metrics["percent"] = bat.percent
                metrics["power_plugged"] = bat.power_plugged
        except Exception:
            pass
            
        return metrics

    def assess(self) -> Dict[str, Any]:
        metrics = self.get_metrics()
        
        if not metrics["has_battery"]:
            return {
                "available_capacity": 100.0,
                "risk_score": 0.0,
                "priority": 1,
                "recommended_action": GovernorAction.NONE,
                "reason": "Battery is not present on this system (running on AC power).",
                "metrics": metrics
            }

        percent = metrics["percent"]
        plugged = metrics["power_plugged"]
        
        # If plugged in, battery is safe
        if plugged:
            return {
                "available_capacity": percent,
                "risk_score": 0.05,
                "priority": 1,
                "recommended_action": GovernorAction.NONE,
                "reason": f"System is plugged in. Battery charge at {percent}%.",
                "metrics": metrics
            }

        # On battery power
        available_capacity = percent

        if percent < 10.0:
            action = GovernorAction.PAUSE
            risk_score = 0.95
            priority = 8
            reason = f"Battery power is critical at {percent}% and discharging."
        elif percent < 25.0:
            action = GovernorAction.ECO
            risk_score = 0.65
            priority = 5
            reason = f"Battery power is low at {percent}% and discharging."
        else:
            action = GovernorAction.NONE
            risk_score = 0.20
            priority = 2
            reason = f"Running on battery. Level is healthy at {percent}%."

        return {
            "available_capacity": available_capacity,
            "risk_score": risk_score,
            "priority": priority,
            "recommended_action": action,
            "reason": reason,
            "metrics": metrics
        }
