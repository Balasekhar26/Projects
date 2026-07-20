class RiskEstimator:
    CRITICAL_KEYWORDS = {"rm", "delete", "remove", "format", "wipe", "drop"}

    @classmethod
    def estimate_risk(cls, command: str) -> float:
        """Computes aggregate execution danger ratings checking system command keywords."""
        words = set(command.lower().strip().split())
        
        # Intersection matches critical commands
        if words.intersection(cls.CRITICAL_KEYWORDS):
            return 0.90
            
        return 0.05
