from datetime import datetime
from backend.core.autonomy.goal_manager import Goal

class PriorityEngine:
    @classmethod
    def calculate_priority_score(cls, goal: Goal) -> float:
        """Calculates dynamic priority score considering baseline priority and deadline proximity."""
        score = float(goal.priority)
        
        if goal.deadline:
            delta = goal.deadline - datetime.now()
            seconds_remaining = delta.total_seconds()
            
            # Close deadlines increase priority score significantly
            if seconds_remaining > 0:
                score += (3600.0 / (seconds_remaining + 1.0)) * 10.0
            else:
                score += 1000.0 # Already past deadline
                
        return score
