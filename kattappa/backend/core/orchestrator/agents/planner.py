"""PlannerAgent — Phase K11 upgrade.

Decomposes goals and registers them in the unified 5-level GoalHierarchy
(Goal Level 1, Subgoal Level 2, Task Level 3).
"""
from __future__ import annotations
from typing import Any
from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event
from backend.agents.planner import PlannerAgent as LegacyPlannerAgent
from backend.core.goal_hierarchy import GoalHierarchy, HierarchyLevel


class PlannerAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Planner"

    def initialize(self) -> None:
        self.legacy_planner = LegacyPlannerAgent()

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("planner_agent_exec", "Planner Agent executing task")
        goal = task.params.get("goal") or context.get("user_input") or ""
        
        goal_id = task.task_id
        
        # ── Register Level 1 GOAL ────────────────────────────────────────────
        try:
            GoalHierarchy.add_node(
                node_id=goal_id,
                parent_id=None,
                level=HierarchyLevel.GOAL,
                title=goal,
                status="ACTIVE",
                progress=0.0,
            )
        except Exception as e:
            log_event("planner_hierarchy_error", f"Error registering goal node: {e}")

        try:
            legacy_graph = self.legacy_planner.decompose(goal, context.to_dict())
            steps = {step_id: step.to_dict() for step_id, step in legacy_graph.steps.items()}
            
            # ── Register Level 3 TASKS under Level 1 GOAL ────────────────────
            for step_id, step in legacy_graph.steps.items():
                try:
                    # Check if there is an intermediate subgoal (optional, fallback to direct parent goal_id)
                    parent_node_id = goal_id
                    
                    GoalHierarchy.add_node(
                        node_id=step_id,
                        parent_id=parent_node_id,
                        level=HierarchyLevel.TASK,
                        title=step.description,
                        status="PROPOSED",
                        progress=0.0,
                        metadata={
                            "agent": step.agent,
                            "action": step.action,
                            "dependencies": step.dependencies,
                        }
                    )
                except Exception as e:
                    log_event("planner_hierarchy_error", f"Error registering task step: {e}")

            context.set("task_graph_steps", steps)
            return TaskResult(success=True, output=steps)
        except Exception as e:
            return TaskResult(success=False, error=str(e))

    def terminate(self, task_id: str) -> None:
        pass
