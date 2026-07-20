from backend.core.autonomy.goal_manager import Goal

class UtilityCalculator:
    @classmethod
    def calculate_utility(cls, goal: Goal, success_probability: float, est_time_sec: float) -> float:
        """Computes executive utility index weighing dynamic success probability against time bounds."""
        base_priority = float(goal.priority)
        
        # Utility score formula: priority * success_rate - resource cost index
        score = (base_priority * success_probability) - (0.01 * est_time_sec)
        return float(score)
