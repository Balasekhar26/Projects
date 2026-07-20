from backend.core.autonomy.goal_manager import Goal
from backend.core.executive.utility_calculator import UtilityCalculator
from backend.core.executive.arbitration_engine import ArbitrationEngine

class ExecutiveController:
    def __init__(self):
        self.utility_calculator = UtilityCalculator()
        self.arbitration_engine = ArbitrationEngine()

    def process_and_arbitrate_goals(self, goals: list[Goal], performance_predictions: dict[str, dict]) -> list[Goal]:
        """Calculates utility scores dynamically and resolves execution schedules order."""
        utilities = {}
        for goal in goals:
            pred = performance_predictions.get(goal.goal_id, {"success_prob": 0.80, "time_sec": 60.0})
            utilities[goal.goal_id] = self.utility_calculator.calculate_utility(
                goal=goal,
                success_probability=pred["success_prob"],
                est_time_sec=pred["time_sec"]
            )
            
        return self.arbitration_engine.resolve_conflicts(goals, utilities)
