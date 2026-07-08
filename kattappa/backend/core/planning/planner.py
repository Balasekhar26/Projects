"""HTN Planner Solver and Validation Engine (Program 5G-2).

Implements recursive decomposition, backtracking search, heuristic ranking,
and plan precondition validation.
"""
from __future__ import annotations

import uuid
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.planning.goal import Goal
from backend.core.planning.task import Task, Operator, Method, Plan, PlannerState

logger = logging.getLogger(__name__)


class HeuristicScorer:
    """Ranks alternative decomposition methods using cost/time metrics."""

    @staticmethod
    def rank_methods(
        methods: List[Method],
        operators: Dict[str, Operator],
    ) -> List[Tuple[float, Method]]:
        """Scores each method by summing the estimated costs of its subtasks.

        Returns list of (score, method) sorted ascending (lower cost = better).
        """
        ranked = []
        for m in methods:
            cost = 0.0
            for sub in m.subtasks:
                op = operators.get(sub)
                if op:
                    cost += op.estimated_cost
                else:
                    cost += 10.0 # Default penalty cost for nested compound tasks
            ranked.append((cost, m))
        return sorted(ranked, key=lambda x: x[0])


class PlanValidator:
    """Validates plan preconditions, constraints, and dependencies before scheduling."""

    @staticmethod
    def validate_plan(plan: Plan, initial_variables: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Walks steps of the plan, updating state variables and verifying preconditions."""
        current_state = dict(initial_variables)
        errors = []

        for idx, op in enumerate(plan.steps):
            # Check preconditions
            for key, val in op.preconditions.items():
                if current_state.get(key) != val:
                    errors.append(
                        f"Step {idx} ({op.name}) failed precondition check: "
                        f"expected {key}={val}, got {current_state.get(key)}"
                    )

            # Apply effects
            current_state.update(op.effects)

        success = len(errors) == 0
        return success, errors


class HTNPlanner:
    """Stateless recursive Hierarchical Task Network planner with backtracking."""

    def __init__(self) -> None:
        self.methods: List[Method] = []
        self.operators: Dict[str, Operator] = {}

    def register_method(self, method: Method) -> None:
        self.methods.append(method)

    def register_operator(self, operator: Operator) -> None:
        self.operators[operator.name] = operator

    def find_plan(self, goal: Goal, initial_state: PlannerState) -> Optional[Plan]:
        """Finds a sequence of primitive operators decomposing the target goal."""
        # High-level task starts with the goal name or target task
        task_list = list(goal.constraints) if goal.constraints else [goal.name]
        
        steps = self._decompose(task_list, initial_state)
        if steps is None:
            return None

        # Compute aggregate metrics
        total_cost = sum(op.estimated_cost for op in steps)
        total_time = sum(op.estimated_time for op in steps)

        plan = Plan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            goal_id=goal.goal_id,
            steps=steps,
            expected_cost=total_cost,
            expected_duration=total_time,
            expected_reward=goal.reward,
            expected_risk=0.05 * len(steps), # Simple risk scalar
            confidence=1.0 - (0.01 * len(steps)),
        )

        return plan

    def _decompose(self, tasks: List[str], state: PlannerState) -> Optional[List[Operator]]:
        """Recursive solver walk."""
        if not tasks:
            return []

        first_task_name = tasks[0]
        remaining_tasks = tasks[1:]

        # 1. If first task is an Operator (primitive)
        if first_task_name in self.operators:
            op = self.operators[first_task_name]
            # Check preconditions
            precond_met = all(state.variables.get(k) == v for k, v in op.preconditions.items())
            if not precond_met:
                return None  # Precondition failed, backtrack

            # Apply effects to cloned state
            next_state = state.clone_with_update(updates=op.effects, complete_task=op.name)
            
            # Decompose remaining
            sub_steps = self._decompose(remaining_tasks, next_state)
            if sub_steps is not None:
                return [op] + sub_steps
            return None

        # 2. If first task is a Compound Task
        # Get matching methods
        matching_methods = [m for m in self.methods if m.task_name == first_task_name]
        if not matching_methods:
            return None  # No decomposition strategy found

        # Rank methods using heuristic scorer
        ranked_methods = HeuristicScorer.rank_methods(matching_methods, self.operators)

        # Check recursion loop
        if first_task_name in state.visited_nodes:
            logger.warning("Recursive decomposition loop detected on task: %s", first_task_name)
            return None

        next_state = state.clone_with_update(visited=first_task_name)

        # Backtracking search over ranked methods
        for _, method in ranked_methods:
            # Check method preconditions
            method_precond_met = all(next_state.variables.get(k) == v for k, v in method.preconditions.items())
            if not method_precond_met:
                continue

            # Decompose method subtasks + remaining tasks
            method_steps = self._decompose(method.subtasks + remaining_tasks, next_state)
            if method_steps is not None:
                return method_steps

        return None
