class HarmPredictor:
    HARMFUL_PATTERNS = {"rm -rf", "format drive", "delete system", "wipe database", "drop table"}

    @classmethod
    def predict_harm(cls, command: str) -> float:
        """Evaluates commands keywords to return a potential harm index between 0.0 and 1.0."""
        cmd_norm = command.lower().strip()
        
        # Check matching patterns
        for pattern in cls.HARMFUL_PATTERNS:
            if pattern in cmd_norm:
                return 0.85
                
        return 0.05
