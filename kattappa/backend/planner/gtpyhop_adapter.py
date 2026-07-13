import time
import uuid
from typing import Any, Dict, List, Optional
from backend.planner.planner_interface import PlannerInterface
from backend.planner.world_state import WorldState
from backend.planner.goal_stack import GoalStack, GoalItem
from backend.planner.belief_store import BeliefStore
from backend.planner.utility_engine import UtilityEngine
from backend.planner.constraint_solver import ConstraintSolver, ConstraintException
from backend.planner.checkpoint_store import CheckpointStore
from backend.planner.task_decomposer import TaskDecomposer

class GTPyhopAdapter(PlannerInterface):
    """Integrates GTPyhop decomposition rules with the unified checkpointing and recovery interfaces."""

    def __init__(self, decomposer: Optional[TaskDecomposer] = None) -> None:
        self.decomposer = decomposer or TaskDecomposer()
        self.goal_stack = GoalStack()
        self.belief_store = BeliefStore()
        
        # Active planner state
        self.active_goal: Optional[str] = None
        self.world_state: WorldState = WorldState()
        self.remaining_plan: List[Dict[str, Any]] = []
        self.completed_tasks: List[str] = []
        self.seed: int = 42
        self.planner_version: str = "1.0.0"

    def create_plan(
        self,
        goal: Any,  # Expected format: GoalItem or goal name string
        world_state: Dict[str, Any],
        constraints: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Decomposes the goal into primitive executable plan steps."""
        self.world_state = WorldState(variables=world_state)
        
        # Populate goal stack
        if isinstance(goal, GoalItem):
            self.active_goal = goal.name
            self.goal_stack.push(goal)
        else:
            self.active_goal = str(goal)
            self.goal_stack.push(GoalItem(
                goal_id=f"g-{uuid.uuid4().hex[:6]}",
                name=self.active_goal,
                priority=constraints.get("priority", "MEDIUM"),
                utility_score=100.0,
                hard_constraints=constraints
            ))

        # Check constraint limits
        ConstraintSolver.validate_temporal_constraints(
            deadline=constraints.get("deadline"),
            timeout=constraints.get("timeout"),
            elapsed_time=0.0,
            start_time=time.time()
        )

        # Decompose the goal using backtracking search
        decomposed_steps = self.decomposer.find_plan(
            self.active_goal,
            self.belief_store,
            self.world_state.variables,
            max_depth=constraints.get("max_depth", 10),
            timeout_limit=constraints.get("timeout", 120.0),
            confidence_threshold=constraints.get("confidence_threshold", 0.85)
        )
        if decomposed_steps is None:
            raise ValueError(f"Planning failed: Goal '{self.active_goal}' could not be decomposed.")
        
        # Build operator plan steps
        self.remaining_plan = []
        for step in decomposed_steps:
            self.remaining_plan.append({
                "step_id": f"step-{uuid.uuid4().hex[:6]}",
                "name": step["name"],
                "preconditions": step["preconditions"],
                "effects": step["effects"],
                "estimated_cost": step["estimated_cost"],
                "estimated_time": step["estimated_time"]
            })

        return {
            "plan_id": f"plan-{uuid.uuid4().hex[:8]}",
            "goal": self.active_goal,
            "steps": list(self.remaining_plan),
            "world_state_hash": self.world_state.get_sha256()
        }

    def execute_step(self, step_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Validates current state constraints, executes the current step, and updates progress cursor."""
        if not self.remaining_plan:
            raise ValueError("Execution error: No remaining plan steps left to execute.")
        
        next_step = self.remaining_plan[0]
        if next_step["step_id"] != step_id:
            raise ValueError(f"Execution error: step_id mismatch. Expected {next_step['step_id']}, got {step_id}")

        self.world_state = WorldState(variables=current_state)

        # Precondition verification
        for key, val in next_step["preconditions"].items():
            if self.world_state.variables.get(key) != val:
                raise ValueError(f"Precondition error for step '{next_step['name']}': Expected {key}={val}, got {self.world_state.variables.get(key)}")

        # Execute step (simulate effect propagation)
        self.remaining_plan.pop(0)
        self.world_state.update(next_step["effects"])
        self.completed_tasks.append(next_step["name"])

        return {
            "status": "COMPLETED",
            "executed_step": next_step["name"],
            "world_state": self.world_state.variables,
            "world_state_hash": self.world_state.get_sha256()
        }

    def checkpoint(self) -> bytes:
        """Serializes current active goal stack, completed lists, and world state."""
        state_dict = {
            "active_goal": self.active_goal,
            "variables": self.world_state.variables,
            "vector_hashes": self.world_state.vector_hashes,
            "remaining_plan": self.remaining_plan,
            "completed_tasks": self.completed_tasks,
            "seed": self.seed,
            "planner_version": self.planner_version
        }
        return CheckpointStore.serialize_state(state_dict)

    def restore(self, checkpoint: bytes) -> None:
        """Restores planning state from compressed checkpoints."""
        state_dict = CheckpointStore.deserialize_state(checkpoint)
        self.active_goal = state_dict["active_goal"]
        self.world_state = WorldState(
            variables=state_dict["variables"],
            vector_hashes=state_dict["vector_hashes"]
        )
        self.remaining_plan = state_dict["remaining_plan"]
        self.completed_tasks = state_dict["completed_tasks"]
        self.seed = state_dict["seed"]
        self.planner_version = state_dict["planner_version"]

    def replan(self, failed_step_id: str, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """Initiates plan recovery starting from the current world state."""
        self.world_state = WorldState(variables=current_state)
        
        # Verify completed tasks whose effects are no longer valid, and discard them
        valid_completed = []
        for task_name in self.completed_tasks:
            task_def = self.decomposer.operators.get(task_name)
            if task_def:
                effects_valid = all(self.world_state.variables.get(k) == v for k, v in task_def.effects.items())
                if effects_valid:
                    valid_completed.append(task_name)
        self.completed_tasks = valid_completed

        # Clear current plan steps and perform redecomposition
        self.remaining_plan = []
        if not self.active_goal:
            raise ValueError("Replanning error: No active goal to replan against.")

        decomposed_steps = self.decomposer.find_plan(
            self.active_goal,
            self.belief_store,
            self.world_state.variables
        )
        if decomposed_steps is None:
            raise ValueError(f"Replanning failed: Goal '{self.active_goal}' could not be decomposed.")
        
        # Build operator plan steps
        for step in decomposed_steps:
            if step["name"] not in self.completed_tasks:
                self.remaining_plan.append({
                    "step_id": f"step-{uuid.uuid4().hex[:6]}",
                    "name": step["name"],
                    "preconditions": step["preconditions"],
                    "effects": step["effects"],
                    "estimated_cost": step["estimated_cost"],
                    "estimated_time": step["estimated_time"]
                })

        return {
            "plan_id": f"plan-{uuid.uuid4().hex[:8]}",
            "goal": self.active_goal,
            "steps": list(self.remaining_plan),
            "world_state_hash": self.world_state.get_sha256()
        }
