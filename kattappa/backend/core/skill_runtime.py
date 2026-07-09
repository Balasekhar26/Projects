"""Skill Runtime (Program 54.0).

Defines first-class executable Skill runtime objects wrapping templates,
validating input keys, executing step commands inside Isolated Sandboxes,
and reporting outcomes to SkillLibrary and EventBus.
"""
from __future__ import annotations

import shlex
from typing import Any, Dict, List, Optional

from backend.core.event_bus import EventBus, EventName
from backend.core.sandbox.local_sandbox import LocalExecutionSandbox
from backend.core.skill_library import SkillLibrary


class Skill:
    """An executable skill wrapper mapping parameters validation and sandboxed runs."""

    def __init__(
        self,
        name: str,
        description: str = "",
        inputs: List[str] | None = None,
        steps: List[str] | None = None,
        outputs: List[str] | None = None,
        required_tools: List[str] | None = None,
        cost_profile: str = "low",
    ) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Skill name cannot be empty")
        
        self.name = name
        self.description = description.strip()
        self.inputs = list(inputs or [])
        self.steps = list(steps or [])
        self.outputs = list(outputs or [])
        self.required_tools = list(required_tools or [])
        self.cost_profile = cost_profile

        # Auto-register template in SkillLibrary if not exists
        if SkillLibrary.get(name) is None:
            SkillLibrary.add_skill(
                name=name,
                description=description,
                inputs=self.inputs,
                steps=self.steps,
                outputs=self.outputs,
                tags=self.required_tools,
            )

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validates inputs, formats parameters, executes steps, and updates library stats."""
        # 1. Input parameters validation
        missing = [key for key in self.inputs if key not in inputs]
        if missing:
            raise ValueError(f"Missing required execution inputs for skill {self.name!r}: {missing}")

        # 2. Publish start event
        EventBus.publish(
            event_name=EventName.EXECUTION_STARTED,
            payload={"skill_name": self.name, "inputs": list(inputs.keys())},
            source="SkillRuntime",
        )

        execution_results = []
        success = True
        failed_step = None
        error_msg = ""

        # 3. Step execution loop
        for step in self.steps:
            try:
                formatted_cmd = step.format(**inputs)
            except KeyError as e:
                success = False
                error_msg = f"Failed to format step: missing key {e}"
                break

            cmd_args = shlex.split(formatted_cmd)
            res = LocalExecutionSandbox.execute_sandboxed_command(cmd_args, timeout=10.0, enable_rollback=True)
            execution_results.append(res)

            if res["returncode"] != 0:
                success = False
                failed_step = step
                error_msg = res["stderr"]
                break

        # 4. Record outcome to SkillLibrary and EventBus
        SkillLibrary.record_result(self.name, success=success)

        EventBus.publish(
            event_name=EventName.EXECUTION_FINISHED if success else EventName.EXECUTION_FAILED,
            payload={
                "skill_name": self.name,
                "success": success,
                "error": error_msg,
                "failed_step": failed_step,
            },
            source="SkillRuntime",
        )

        if success:
            # Gather output parameters (maps output keys to standard stdout streams)
            out_payload = {}
            for out_key in self.outputs:
                # Basic output mapper: maps output keys to stdout of execution results
                if execution_results:
                    out_payload[out_key] = execution_results[-1]["stdout"].strip()
            
            return {
                "status": "success",
                "outputs": out_payload,
                "steps_run": len(execution_results),
            }
        else:
            return {
                "status": "failed",
                "reason": error_msg,
                "failed_step": failed_step,
                "steps_run": len(execution_results),
            }
