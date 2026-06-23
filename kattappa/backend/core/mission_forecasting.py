from __future__ import annotations

from typing import Any

from backend.core.mission_state import MissionState
from backend.core.failure_recovery import FailureRecoveryEngine


class MissionForecasting:
    @classmethod
    def get_forecast(cls, mission_id: str) -> dict[str, Any]:
        """Calculates completion, risk, success probability, and time remaining forecasts."""
        state = MissionState.get_state(mission_id)
        if not state:
            return {
                "completion_percentage": 0.0,
                "risk_score": 10.0,
                "success_probability": 90.0,
                "time_remaining_minutes": 120.0
            }

        progress = state.get("progress", 0.0)
        blocked = state.get("blocked", False)
        
        # Calculate risk and success scores based on blockers and failures
        failures = FailureRecoveryEngine.load_failures()
        mission_failures = [f for f in failures if f["mission_id"] == mission_id and not f["resolved"]]
        
        base_risk = 10.0
        base_success = 95.0
        
        if blocked:
            base_risk += 30.0
            base_success -= 20.0
            
        # Add risk for active failures
        base_risk += len(mission_failures) * 15.0
        base_success -= len(mission_failures) * 10.0
        
        # Clamp bounds
        risk_score = max(0.0, min(100.0, base_risk))
        success_probability = max(0.0, min(100.0, base_success))
        
        # Calculate time remaining
        remaining_stages_count = len(state.get("pending_stages", []))
        time_factor = 25.0  # 25 minutes per stage average
        time_remaining = (100.0 - progress) * 2.0
        
        if blocked:
            time_remaining += 45.0  # Add penalty for blocks
            
        return {
            "completion_percentage": round(progress, 1),
            "risk_score": round(risk_score, 1),
            "success_probability": round(success_probability, 1),
            "time_remaining_minutes": round(max(5.0, time_remaining), 1)
        }
