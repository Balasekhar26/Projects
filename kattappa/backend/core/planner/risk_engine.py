from __future__ import annotations

class RiskEngine:
    @classmethod
    def estimate_risk(cls, action: str, params: dict) -> str:
        """Classifies risk level (LOW, MEDIUM, HIGH) of a task action based on parameters."""
        act_upper = action.upper()
        
        if "DELETE" in act_upper or "REMOVE" in act_upper or "CLEAN" in act_upper:
            return "HIGH"
            
        if "INSTALL" in act_upper or "WRITE" in act_upper or "SHELL" in act_upper:
            return "MEDIUM"
            
        return "LOW"
