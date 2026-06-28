from __future__ import annotations
from typing import Any
from backend.core.orchestrator.base import BaseAgent, Task, TaskResult
from backend.core.orchestrator.context import SharedContext
from backend.core.logger import log_event
from backend.core.action_broker import ActionBroker

class ToolExecutorAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Tool Executor"

    def initialize(self) -> None:
        pass

    def execute(self, task: Task, context: SharedContext) -> TaskResult:
        log_event("tool_agent_exec", "Tool Executor Agent executing task")
        action = task.params.get("action") or task.action
        params = task.params.get("params") or task.params
        
        tool_node_id = f"{task.task_id}_tool_{action}"
        action_node_id = f"{task.task_id}_action"
        try:
            from backend.core.goal_hierarchy import GoalHierarchy, HierarchyLevel
            GoalHierarchy.add_node(
                node_id=tool_node_id,
                parent_id=action_node_id,
                level=HierarchyLevel.TOOL_CALL,
                title=f"Call tool {action}",
                status="ACTIVE",
                progress=0.1,
                metadata={"params": params}
            )
        except Exception as e:
            log_event("tool_agent_hierarchy_error", f"Error registering tool node: {e}")

        try:
            state = context.to_dict()
            res = ActionBroker.intake_request("OrchestrationAgent", action, params, state)
            if res.get("success"):
                try:
                    from backend.core.goal_hierarchy import GoalHierarchy
                    GoalHierarchy.update_node(tool_node_id, status="COMPLETED", progress=1.0)
                except Exception as e:
                    log_event("tool_agent_hierarchy_error", f"Error updating tool node success: {e}")
                return TaskResult(success=True, output=res.get("result"))
            else:
                try:
                    from backend.core.goal_hierarchy import GoalHierarchy
                    GoalHierarchy.update_node(tool_node_id, status="FAILED", progress=0.0)
                except Exception as e:
                    log_event("tool_agent_hierarchy_error", f"Error updating tool node failure: {e}")
                return TaskResult(success=False, error=res.get("error") or "Execution failed")
        except Exception as e:
            try:
                from backend.core.goal_hierarchy import GoalHierarchy
                GoalHierarchy.update_node(tool_node_id, status="FAILED", progress=0.0)
            except Exception as ex:
                log_event("tool_agent_hierarchy_error", f"Error updating tool node failure: {ex}")
            return TaskResult(success=False, error=str(e))

    def terminate(self, task_id: str) -> None:
        pass
