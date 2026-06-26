"""
Kattappa Autonomous Workflow Engine — Step 28
===============================================

Closes the gap from planning to execution.

Pipeline:
    Goal → Planner → ToolRouter → Monitor → Replan → Reflect → Learn

Public API:
    from kattappa_runtime.workflow import WorkflowEngine, ToolRouter

    router = ToolRouter(research_engine=research, memory=mem)
    engine = WorkflowEngine(planner_engine=planner, tool_router=router,
                            dry_run=False, max_steps=20, max_replans=2)

    result = engine.run("Research impedance matching", domain="rf_systems")
    print(result.execution_log())
"""

from kattappa_runtime.workflow.engine import WorkflowEngine
from kattappa_runtime.workflow.router import ToolRouter
from kattappa_runtime.workflow.schema import (
    WorkflowResult, WorkflowEvent, WorkflowStatus, EventType
)

__all__ = [
    "WorkflowEngine",
    "ToolRouter",
    "WorkflowResult", "WorkflowEvent", "WorkflowStatus", "EventType",
]
