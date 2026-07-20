class RiskEstimator:
    def __init__(self):
        pass

    def estimate_action_risk(self, action_command: str) -> float:
        """Calculates risk score (probability * impact) of a desktop actuator command."""
        cmd_clean = action_command.lower().strip()
        
        # High impact commands
        if any(w in cmd_clean for w in ["delete", "rm", "format", "registry", "drop"]):
            probability_of_failure = 0.5
            impact_severity = 0.9
        else:
            probability_of_failure = 0.1
            impact_severity = 0.2
            
        return float(probability_of_failure * impact_severity)
