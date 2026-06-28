import sys
import psutil
import subprocess
from typing import Dict, Any
from backend.core.governor.base import BaseGovernor, GovernorAction

class ThermalGovernor(BaseGovernor):
    """
    Monitors system temperature and Apple Silicon thermal pressure
    to prevent hardware thermal throttling and kernel-level shutdown.
    """
    
    def __init__(self):
        super().__init__(priority=100)

    def get_metrics(self) -> Dict[str, Any]:
        cpu = psutil.cpu_percent(interval=None)
        if cpu == 0.0:
            cpu = psutil.cpu_percent(interval=0.1)

        # Baseline heuristic
        temp_c = 40.0 + (cpu * 0.4)
        
        # Try to factor in GPU
        try:
            import torch
            if torch.backends.mps.is_available():
                allocated = torch.mps.driver_allocated_memory()
                if allocated > 0:
                    temp_c += 15.0
        except Exception:
            pass

        pmset_warning = False
        if sys.platform == "darwin":
            try:
                out = subprocess.check_output(["pmset", "-g", "therm"], text=True)
                if "CPU_Speed_Limit" in out or "Scheduler_Limit" in out:
                    for line in out.splitlines():
                        if "CPU_Speed_Limit" in line and not "100" in line:
                            pmset_warning = True
                            temp_c = max(temp_c, 75.0)
            except Exception:
                pass

        return {
            "temperature_c": round(temp_c, 1),
            "thermal_warning": pmset_warning
        }

    def assess(self) -> Dict[str, Any]:
        metrics = self.get_metrics()
        temp_c = metrics["temperature_c"]
        warning = metrics["thermal_warning"]
        
        available_capacity = max(0.0, 100.0 - temp_c)
        
        if temp_c >= 80.0 or warning:
            action = GovernorAction.PAUSE
            risk_score = 0.90
            reason = f"Thermal pressure is critical ({temp_c}C). Imminent hardware throttling detected."
        elif temp_c >= 70.0:
            action = GovernorAction.ECO
            risk_score = 0.60
            reason = f"Thermal load is elevated ({temp_c}C). Entering ECO mode to reduce wattage."
        else:
            action = GovernorAction.NONE
            risk_score = 0.10
            reason = f"Thermal status is nominal ({temp_c}C)."

        return {
            "available_capacity": available_capacity,
            "risk_score": risk_score,
            "priority": self.priority,
            "confidence": self.confidence,
            "recommended_action": action,
            "reason": reason,
            "metrics": metrics
        }
