import json
from pathlib import Path
from typing import Dict, Any
from backend.core.governor.base import BaseGovernor, GovernorAction
from backend.core.config import runtime_data_root

class NetworkGovernor(BaseGovernor):
    """
    Monitors cumulative network download bytes and requests to prevent
    exceeding network caps and rate limits.
    """
    
    LIMIT_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
    LIMIT_REQUESTS = 100

    def __init__(self):
        super().__init__(priority=20)

    def _get_db_path(self) -> Path:
        return runtime_data_root() / "backend" / "data" / "resource_governance.json"

    def get_metrics(self) -> Dict[str, Any]:
        metrics = {
            "download_bytes": 0,
            "requests_count": 0
        }
        db_path = self._get_db_path()
        if db_path.exists():
            try:
                with open(db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    metrics["download_bytes"] = data.get("network_download_bytes", 0)
                    metrics["requests_count"] = data.get("network_requests", 0)
            except Exception:
                pass
        return metrics

    def assess(self) -> Dict[str, Any]:
        metrics = self.get_metrics()
        dl_bytes = metrics["download_bytes"]
        req_count = metrics["requests_count"]

        # Calculate capacities as percentage remaining
        bytes_pct = (dl_bytes / self.LIMIT_DOWNLOAD_BYTES) * 100.0 if self.LIMIT_DOWNLOAD_BYTES > 0 else 100.0
        reqs_pct = (req_count / self.LIMIT_REQUESTS) * 100.0 if self.LIMIT_REQUESTS > 0 else 100.0
        
        max_usage_pct = max(bytes_pct, reqs_pct)
        available_capacity = max(0.0, 100.0 - max_usage_pct)

        if req_count >= self.LIMIT_REQUESTS:
            action = GovernorAction.PAUSE
            risk_score = 0.95
            reason = f"Network requests limit reached ({req_count} / {self.LIMIT_REQUESTS})."
        elif dl_bytes >= self.LIMIT_DOWNLOAD_BYTES:
            action = GovernorAction.PAUSE
            risk_score = 0.95
            reason = f"Network download quota exhausted ({dl_bytes / (1024*1024):.2f} MB / {self.LIMIT_DOWNLOAD_BYTES / (1024*1024):.0f} MB)."
        elif req_count > (self.LIMIT_REQUESTS * 0.85) or dl_bytes > (self.LIMIT_DOWNLOAD_BYTES * 0.85):
            action = GovernorAction.ECO
            risk_score = 0.60
            reason = f"Network usage is elevated (Requests: {req_count}, Downloads: {dl_bytes / (1024*1024):.2f} MB)."
        else:
            action = GovernorAction.NONE
            risk_score = 0.10
            reason = "Network quotas are healthy."

        return {
            "available_capacity": available_capacity,
            "risk_score": risk_score,
            "priority": self.priority,
            "confidence": self.confidence,
            "recommended_action": action,
            "reason": reason,
            "metrics": metrics
        }
