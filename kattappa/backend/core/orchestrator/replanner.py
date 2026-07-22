from __future__ import annotations
import json
import os
from typing import Any
from backend.core.orchestrator.base import Task
from backend.core.orchestrator.task_graph import TaskGraph
from backend.core.logger import log_event
from backend.core.model_router import ask_model

class FailureReplanner:
    @classmethod
    def analyze_and_replan(
        cls,
        graph: TaskGraph,
        failed_task: Task,
        error_msg: str,
        context: Any
    ) -> bool:
        """
        Analyzes the failure of failed_task. 
        Inserts corrective tasks into the graph dynamically if a recovery strategy is found.
        Returns True if replanning succeeded (graph modified), False otherwise.
        """
        log_event(
            "replanner_start",
            f"Replanner analyzing failure of task {failed_task.task_id} ({failed_task.action}): {error_msg}"
        )
        
        # Determine if we should use mock replanning (tests) or dynamic LLM replanning
        import sys
        use_mock = (
            os.getenv("KATTAPPA_ENV") == "test" or 
            os.getenv("KATTAPPA_TEST_MODE") == "true" or
            os.getenv("KATTAPPA_MOCK_LLM") == "true"
        )
        
        corrective_steps = []
        
        if use_mock:
            # Deterministic mock scenarios for tests
            action_lower = failed_task.action.lower()
            params_str = str(failed_task.params).lower()
            err_lower = error_msg.lower()
            
            if "pip" in action_lower or "pip install" in params_str or "install" in action_lower:
                corrective_steps = [
                    {
                        "task_id": f"recover_venv_{failed_task.task_id}",
                        "agent_name": "Tool Executor",
                        "action": "RUN_SHELL",
                        "params": {"command": "python -m venv venv"},
                        "description": "Create local virtual environment"
                    }
                ]
            elif "permission" in err_lower or "access denied" in err_lower or "unauthorized" in err_lower:
                corrective_steps = [
                    {
                        "task_id": f"recover_perm_{failed_task.task_id}",
                        "agent_name": "Tool Executor",
                        "action": "RUN_SHELL",
                        "params": {"command": "echo Retrying with permissions"},
                        "description": "Fix execution permissions"
                    }
                ]
        else:
            # Production Mode: Elicit corrective tasks from the LLM
            prompt = (
                f"A task execution graph encountered a failure.\n"
                f"Goal of the execution run: {getattr(graph, 'goal', 'unknown')}\n"
                f"Failed Task Action: {failed_task.action}\n"
                f"Failed Task Params: {failed_task.params}\n"
                f"Error Message: {error_msg}\n\n"
                f"Propose corrective task steps to run BEFORE we retry this failed task.\n"
                f"Output ONLY a valid JSON array of objects. Each object must contain:\n"
                f"- task_id (string, must be unique)\n"
                f"- agent_name (string, e.g. 'Tool Executor')\n"
                f"- action (string, e.g. 'RUN_SHELL', 'WRITE_FILE')\n"
                f"- params (dict)\n"
                f"- description (string)\n"
                f"Example: "
                f'[{"task_id": "fix_pip", "agent_name": "Tool Executor", "action": "RUN_SHELL", "params": {"command": "pip install --user flask"}, "description": "install with user flag"}]'
            )
            try:
                res = ask_model(prompt, role="planning")
                clean_res = res.strip()
                if clean_res.startswith("```json"):
                    clean_res = clean_res[7:]
                if clean_res.endswith("```"):
                    clean_res = clean_res[:-3]
                clean_res = clean_res.strip()
                corrective_steps = json.loads(clean_res)
            except Exception as e:
                log_event("replanner_llm_error", f"LLM failed to generate recovery steps: {e}")
                return False
                
        if not corrective_steps:
            log_event("replanner_no_steps", "No corrective steps determined. Aborting replan.")
            return False
            
        # Modify the TaskGraph to inject the recovery tasks
        try:
            # 1. Save original dependencies of failed task
            orig_deps = list(failed_task.dependencies)
            
            # 2. Add each corrective task to the graph
            import uuid
            prev_recovery_id = None
            for idx, step in enumerate(corrective_steps):
                unique_task_id = f"{step['task_id']}_{uuid.uuid4().hex[:6]}"
                rec_task = Task(
                    task_id=unique_task_id,
                    agent_name=step["agent_name"],
                    action=step["action"],
                    params=step["params"]
                )
                rec_task.status = "PENDING"
                rec_task.priority = failed_task.priority + 0.1
                
                if idx == 0:
                    rec_task.dependencies = list(orig_deps)
                else:
                    rec_task.dependencies = [prev_recovery_id]
                
                graph.add_task(rec_task)
                prev_recovery_id = rec_task.task_id
                
            # 3. Update the failed task's dependency to depend on the final recovery task
            failed_task.dependencies = [prev_recovery_id]
            graph.dependencies[failed_task.task_id] = [prev_recovery_id]
            
            # 4. Reset the failed task status to PENDING and reset retry count
            failed_task.status = "PENDING"
            failed_task.retry_count = 0
            failed_task.error = None
            
            log_event(
                "replanner_success",
                f"Successfully replanned! Injected {len(corrective_steps)} recovery steps before retrying {failed_task.task_id}"
            )
            return True
        except Exception as e:
            log_event("replanner_injection_error", f"Failed to inject recovery steps into graph: {e}")
            return False
