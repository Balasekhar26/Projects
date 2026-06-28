import json
import psutil
from pathlib import Path
from typing import Dict, Any
from backend.core.governor.base import BaseGovernor, GovernorAction
from backend.core.config import runtime_data_root

class DiskGovernor(BaseGovernor):
    """
    Monitors workspace disk writes and physical SSD space availability
    to prevent file system saturation and data corruption.
    """
    
    LIMIT_WRITE_BYTES = 100 * 1024 * 1024  # 100 MB
    MIN_FREE_PHYSICAL_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB

    def _get_db_path(self) -> Path:
        return runtime_data_root() / "backend" / "data" / "resource_governance.json"

    def get_metrics(self) -> Dict[str, Any]:
        metrics = {
            "bytes_written": 0,
            "physical_free_bytes": 0
        }
        db_path = self._get_db_path()
        if db_path.exists():
            try:
                with open(db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    metrics["bytes_written"] = data.get("disk_used_bytes", 0)
            except Exception:
                pass
                
        try:
            # Check free space on the current drive
            usage = psutil.disk_usage(str(runtime_data_root()))
            metrics["physical_free_bytes"] = usage.free
        except Exception:
            try:
                usage = psutil.disk_usage("/")
                metrics["physical_free_bytes"] = usage.free
            except Exception:
                pass
                
        return metrics

    def assess(self) -> Dict[str, Any]:
        metrics = self.get_metrics()
        written = metrics["bytes_written"]
        free_bytes = metrics["physical_free_bytes"]

        # Calculate workspace capacity
        workspace_used_pct = (written / self.LIMIT_WRITE_BYTES) * 100.0 if self.LIMIT_WRITE_BYTES > 0 else 100.0
        
        # Calculate physical capacity
        physical_free_pct = (free_bytes / self.MIN_FREE_PHYSICAL_BYTES) * 100.0 if self.MIN_FREE_PHYSICAL_BYTES > 0 else 100.0
        
        available_capacity = max(0.0, 100.0 - workspace_used_pct)

        if free_bytes > 0 and free_bytes < self.MIN_FREE_PHYSICAL_BYTES:
            action = GovernorAction.PAUSE
            risk_score = 0.98
            priority = 9
            reason = f"Physical disk space is critically low at {free_bytes / (1024**3):.2f} GB (minimum required: {self.MIN_FREE_PHYSICAL_BYTES / (1024**3):.0f} GB)."
        elif written >= self.LIMIT_WRITE_BYTES:
            action = GovernorAction.PAUSE
            risk_score = 0.95
            priority = 8
            reason = f"Workspace disk write quota exceeded ({written / (1024*1024):.2f} MB / {self.LIMIT_WRITE_BYTES / (1024*1024):.0f} MB)."
        elif written > (self.LIMIT_WRITE_BYTES * 0.85):
            action = GovernorAction.ECO
            risk_score = 0.60
            priority = 4
            reason = f"Workspace disk write quota is nearing limit ({written / (1024*1024):.2f} MB)."
        else:
            action = GovernorAction.NONE
            risk_score = 0.10
            priority = 1
            reason = "Disk space and quotas are healthy."

        return {
            "available_capacity": available_capacity,
            "risk_score": risk_score,
            "priority": priority,
            "recommended_action": action,
            "reason": reason,
            "metrics": metrics
        }
