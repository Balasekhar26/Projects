from __future__ import annotations
from backend.agents.planner import TaskGraph, TaskStep

class SkillExecutor:
    @classmethod
    def execute_skill(cls, skill: dict, goal: str) -> TaskGraph:
        """Instantiates a TaskGraph directly using cached skill action templates."""
        graph = TaskGraph(goal)
        action_sequence = skill.get("action_sequence") or []
        for step_dict in action_sequence:
            step = TaskStep(
                step_id=step_dict["step_id"],
                description=step_dict["description"],
                agent=step_dict["agent"],
                action=step_dict["action"],
                params=step_dict.get("params") or {},
                dependencies=step_dict.get("dependencies") or []
            )
            graph.add_step(step)
        return graph
