from __future__ import annotations

class ConsensusEngine:
    @classmethod
    def resolve(cls, confidence: float) -> str:
        """Determines the consensus decision based on the final aggregated confidence threshold."""
        if confidence >= 0.85:
            return "EXECUTE"
        elif confidence >= 0.60:
            return "ASK_USER_APPROVAL"
        else:
            return "REJECT_AND_REPLAN"
