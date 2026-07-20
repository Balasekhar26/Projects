from backend.core.meta.assumption_tracker import AssumptionTracker
from backend.core.meta.strategy_evaluator import StrategyEvaluator

class MetaReasoner:
    def __init__(self):
        self.assumption_tracker = AssumptionTracker()
        self.strategy_evaluator = StrategyEvaluator()
        self.command_history = []

    def log_action(self, command: str) -> None:
        """Logs command execution into history for loops analysis."""
        self.command_history.append(command.lower().strip())

    def detect_logical_loops(self) -> bool:
        """Intercepts repetitive action execution cycles indicating planning logic loops."""
        if len(self.command_history) < 3:
            return False
            
        # Check if the last 3 commands are exactly identical
        last_three = self.command_history[-3:]
        return len(set(last_three)) == 1
