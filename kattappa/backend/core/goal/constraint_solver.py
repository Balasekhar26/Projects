from datetime import datetime
from backend.core.autonomy.goal_manager import Goal

class ConstraintSolver:
    @classmethod
    def validate_constraints(cls, goal: Goal, available_budget: float = 500000.0) -> bool:
        """Evaluates goal constraints (deadlines, budgets) and returns True if valid."""
        # 1. Check if deadline has passed
        if goal.deadline and goal.deadline < datetime.now():
            return False
            
        # 2. Check cost limits/budgets (e.g. max ₹5 lakh)
        # Mock constraint check: if goal objective mentions cost exceeding limit, reject it
        if "budget" in goal.objective.lower():
            try:
                # Simple parser for mock tests
                parts = goal.objective.lower().split()
                for part in parts:
                    if part.isdigit() and float(part) > available_budget:
                        return False
            except Exception:
                pass
                
        return True
