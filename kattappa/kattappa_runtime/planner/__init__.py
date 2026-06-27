"""
Kattappa Planner Evolution — Step 27
======================================

Mini project manager inside Kattappa.

Pipeline position:
    Goal → Decompose → Plan Alternatives → Select → Monitor → Execute → Reflect → Learn

Public API:
    from kattappa_runtime.planner import PlannerEngine

    planner = PlannerEngine(
        memory=memory,
        reflection_engine=reflection_engine,
        learning_engine=learning_engine,
        tool_mastery=tool_mastery,
    )

    goal   = planner.submit("Research impedance matching", domain="rf_systems")
    planner.activate(goal.goal_id)

    for task in planner.get_ready_tasks(goal.goal_id):
        # Execute task...
        planner.mark_task_done(goal.goal_id, goal.selected_plan_id, task.task_id,
                               result="Found relevant material.")

    print(planner.progress_report(goal.goal_id))
"""

import warnings

warnings.warn(
    "kattappa_runtime.planner is deprecated and will be removed in K5. Use backend.core.executive_planner.py instead.",
    DeprecationWarning,
    stacklevel=2
)

from kattappa_runtime.planner.engine     import PlannerEngine
from kattappa_runtime.planner.schema     import (
    Goal, Plan, Task,
    TaskStatus, RiskLevel, PlanStatus
)
from kattappa_runtime.planner.store      import PlannerStore
from kattappa_runtime.planner.decomposer import GoalDecomposer
from kattappa_runtime.planner.monitor    import PlanMonitor, PlanHealth

__all__ = [
    "PlannerEngine",
    "Goal", "Plan", "Task",
    "TaskStatus", "RiskLevel", "PlanStatus",
    "PlannerStore",
    "GoalDecomposer",
    "PlanMonitor", "PlanHealth",
]
