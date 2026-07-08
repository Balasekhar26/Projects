import torch
import psutil
from typing import Dict, Any
from backend.core.governor.base import BaseGovernor, GovernorAction

class GpuGovernor(BaseGovernor):
    """
    Monitors Apple Silicon MPS (Metal Performance Shaders) VRAM usage
    and driver allocation limits to prevent GPU out-of-memory events.
    """
    
    def __init__(self):
        super().__init__(priority=70)

    def get_metrics(self) -> Dict[str, Any]:
        metrics = {
            "mps_available": False,
            "allocated_gb": 0.0,
            "recommended_max_gb": 0.0,
            "gpu_usage_percent": 0.0
        }
        
        if torch.backends.mps.is_available():
            metrics["mps_available"] = True
            try:
                allocated = torch.mps.driver_allocated_memory()
                metrics["allocated_gb"] = allocated / (1024 ** 3)
                
                if hasattr(torch.mps, "recommended_max_memory"):
                    recommended = torch.mps.recommended_max_memory()
                    metrics["recommended_max_gb"] = recommended / (1024 ** 3)
                else:
                    total_ram = psutil.virtual_memory().total
                    metrics["recommended_max_gb"] = (total_ram * 0.6) / (1024 ** 3)
                
                if metrics["recommended_max_gb"] > 0:
                    metrics["gpu_usage_percent"] = (metrics["allocated_gb"] / metrics["recommended_max_gb"]) * 100.0
            except Exception:
                pass
        return metrics

    def assess(self) -> Dict[str, Any]:
        metrics = self.get_metrics()
        
        if not metrics["mps_available"]:
            return {
                "available_capacity": 100.0,
                "risk_score": 0.0,
                "priority": self.priority,
                "confidence": 0.0,  # Sensor has 0 confidence since GPU is not active/available
                "recommended_action": GovernorAction.NONE,
                "reason": "MPS (Metal Performance Shaders) is not active or available on this platform.",
                "metrics": metrics
            }

        usage_pct = metrics["gpu_usage_percent"]
        available_capacity = max(0.0, 100.0 - usage_pct)

        if usage_pct > 90.0:
            action = GovernorAction.PAUSE
            risk_score = 0.95
            reason = f"GPU VRAM usage is critical at {metrics['allocated_gb']:.2f} GB / {metrics['recommended_max_gb']:.2f} GB ({usage_pct:.1f}%)."
        elif usage_pct > 75.0:
            action = GovernorAction.ECO
            risk_score = 0.70
            reason = f"GPU VRAM usage is elevated at {metrics['allocated_gb']:.2f} GB / {metrics['recommended_max_gb']:.2f} GB ({usage_pct:.1f}%)."
        else:
            action = GovernorAction.NONE
            risk_score = 0.10
            reason = f"GPU VRAM usage is nominal at {metrics['allocated_gb']:.2f} GB / {metrics['recommended_max_gb']:.2f} GB ({usage_pct:.1f}%)."

        return {
            "available_capacity": available_capacity,
            "risk_score": risk_score,
            "priority": self.priority,
            "confidence": self.confidence,
            "recommended_action": action,
            "reason": reason,
            "metrics": metrics
        }
