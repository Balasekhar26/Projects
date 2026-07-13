from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from backend.planner.belief_store import BeliefStore
from backend.planner.utility_engine import UtilityEngine

class Operator:
    """Represents a primitive planning operation with preconditions, effects, and metrics."""

    def __init__(
        self,
        name: str,
        preconditions: Dict[str, Any],
        effects: Dict[str, Any],
        estimated_cost: float = 1.0,
        estimated_time: float = 1.0
    ) -> None:
        self.name = name
        self.preconditions = preconditions
        self.effects = effects
        self.estimated_cost = estimated_cost
        self.estimated_time = estimated_time


class Method:
    """Represents a decomposition strategy for compound tasks."""

    def __init__(
        self,
        name: str,
        task_name: str,
        preconditions: Dict[str, Any],
        subtasks: List[str],
        reward: float = 100.0,
        failure_penalty: float = 0.0
    ) -> None:
        self.name = name
        self.task_name = task_name
        self.preconditions = preconditions
        self.subtasks = subtasks
        self.reward = reward
        self.failure_penalty = failure_penalty


class TaskDecomposer:
    """Performs backtracking search over registered operators and alternative utility-ranked methods."""

    def __init__(self) -> None:
        self.operators: Dict[str, Operator] = {}
        self.methods: List[Method] = []

    def declare_operator(self, op: Operator) -> None:
        """Declares a primitive operator, matching GTPyhop api layout."""
        self.operators[op.name] = op

    def declare_method(self, method: Method) -> None:
        """Declares a decomposition method, matching GTPyhop api layout."""
        self.methods.append(method)

    def find_plan(
        self,
        goal_task: str,
        belief_store: BeliefStore,
        initial_state: Dict[str, Any],
        max_depth: int = 10,
        timeout_limit: float = 120.0,
        confidence_threshold: float = 0.85
    ) -> Optional[List[Dict[str, Any]]]:
        """Decomposes a compound task into primitive operators using utility-ranked backtracking search."""
        visited_nodes: Set[str] = set()

        def search(
            tasks: List[str],
            current_state: Dict[str, Any],
            cumulative_time: float,
            depth: int
        ) -> Optional[List[Dict[str, Any]]]:
            if depth > max_depth:
                return None
            if cumulative_time > timeout_limit:
                return None
            if not tasks:
                return []

            task_name = tasks[0]
            remaining = tasks[1:]

            # Case 1: Primitive Operator
            if task_name in self.operators:
                op = self.operators[task_name]
                # Precondition verification checking belief store confidence
                for key, val in op.preconditions.items():
                    belief_res = belief_store.get_belief(key)
                    if belief_res is not None:
                        b_val, b_conf = belief_res
                        if b_val != val or b_conf < confidence_threshold:
                            return None
                    else:
                        if current_state.get(key) != val:
                            return None

                # Preconditions met: simulate effects
                next_state = dict(current_state)
                next_state.update(op.effects)

                # Recursively plan remaining tasks
                sub_plan = search(remaining, next_state, cumulative_time + op.estimated_time, depth)
                if sub_plan is not None:
                    step_repr = {
                        "name": op.name,
                        "preconditions": op.preconditions,
                        "effects": op.effects,
                        "estimated_cost": op.estimated_cost,
                        "estimated_time": op.estimated_time
                    }
                    return [step_repr] + sub_plan
                return None

            # Case 2: Compound Task
            matching_methods = [m for m in self.methods if m.task_name == task_name]
            if not matching_methods:
                return None

            # Evaluate utility for each matching method
            method_utilities: List[Tuple[float, Method]] = []
            for m in matching_methods:
                precond_met = True
                for key, val in m.preconditions.items():
                    belief_res = belief_store.get_belief(key)
                    if belief_res is not None:
                        b_val, b_conf = belief_res
                        if b_val != val or b_conf < confidence_threshold:
                            precond_met = False
                            break
                    else:
                        if current_state.get(key) != val:
                            precond_met = False
                            break
                if not precond_met:
                    continue

                # Estimate cumulative time and cost of subtasks
                est_cost = 0.0
                est_time = 0.0
                for sub in m.subtasks:
                    if sub in self.operators:
                        op = self.operators[sub]
                        est_cost += op.estimated_cost
                        est_time += op.estimated_time
                    else:
                        est_cost += 10.0
                        est_time += 10.0

                # Compute utility score
                utility = UtilityEngine.calculate_utility(
                    reward=m.reward,
                    success_probability=0.95,
                    estimated_cost=est_cost,
                    estimated_time=est_time,
                    failure_penalty=m.failure_penalty
                )
                method_utilities.append((utility, m))

            # Rank alternative methods by utility score (highest utility first)
            method_utilities.sort(key=lambda x: x[0], reverse=True)

            if task_name in visited_nodes:
                return None
            visited_nodes.add(task_name)

            for utility, method in method_utilities:
                # Prune branch if utility falls below threshold
                if UtilityEngine.should_prune_branch(utility, minimum_utility_threshold=0.0):
                    continue

                # Recurse and expand method subtasks
                sub_plan = search(method.subtasks + remaining, current_state, cumulative_time, depth + 1)
                if sub_plan is not None:
                    visited_nodes.remove(task_name)
                    return sub_plan

            visited_nodes.remove(task_name)
            return None

        # Execute backtracking search
        return search([goal_task], dict(initial_state), 0.0, 1)
