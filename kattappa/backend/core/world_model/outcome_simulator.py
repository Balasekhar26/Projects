class OutcomeSimulator:
    def __init__(self):
        pass

    def simulate_plan_success(self, steps: list[dict], single_step_prob: float = 0.95) -> float:
        """Simulates success probability outcomes of plan steps sequentially."""
        if not steps:
            return 1.0
            
        # Joint probability = single_step_prob ^ steps count
        # In production, this pulls historical success statistics from SQLite memory
        return float(single_step_prob ** len(steps))
