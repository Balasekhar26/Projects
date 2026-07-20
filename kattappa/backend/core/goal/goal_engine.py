from backend.core.autonomy.goal_manager import Goal
from backend.core.goal.priority_engine import PriorityEngine
from backend.core.goal.constraint_solver import ConstraintSolver
from backend.core.goal.dependency_resolver import DependencyResolver

class GoalEngine:
    def __init__(self):
        self.priority_engine = PriorityEngine()
        self.constraint_solver = ConstraintSolver()
        self.dependency_resolver = DependencyResolver()

    def orchestrate_goals(self, goals: list[Goal], subgoal_deps: dict[str, list[str]]) -> list[str]:
        """Validates constraints, computes dynamic priority weights, and sorts goal execution lists."""
        # 1. Filter goals violating constraints
        valid_goals = [g for g in goals if self.constraint_solver.validate_constraints(g)]
        
        # 2. Sort by dynamic priority scores (highest first)
        valid_goals.sort(key=lambda g: self.priority_engine.calculate_priority_score(g), reverse=True)
        
        # 3. Resolve dependency mappings order
        ordered_ids = self.dependency_resolver.resolve_execution_order(subgoal_deps)
        
        # Intersection to ensure we only return valid scheduled goals in topological order
        valid_ids = {g.goal_id for g in valid_goals}
        return [gid for gid in ordered_ids if gid in valid_ids]
