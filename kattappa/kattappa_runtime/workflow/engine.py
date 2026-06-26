"""
Autonomous Workflow Engine — Step 28 Core
==========================================

The WorkflowEngine is the first complete autonomous execution loop
in Kattappa's architecture.

It closes the final gap between planning and doing:

    Goal (human-provided)
      ↓ PlannerEngine.submit()
    Plan alternatives generated
      ↓ activate best plan
    Autonomous execution loop:
      ├─ get_ready_tasks()
      ├─ ToolRouter.execute(task)
      ├─ mark_task_done() or mark_task_failed()
      ├─ PlanMonitor.check() → health assessment
      ├─ if needs_replan → PlannerEngine.replan()
      └─ repeat until complete / failed / safety_halt
      ↓ on completion:
    ReflectionEngine.reflect()
    LearningEngine.learn_from()
    Memory.store_episode()

Safety controls:
  - max_steps:    hard limit on total task executions per run
  - max_replans:  maximum number of mid-run replan cycles
  - dry_run:      all HIGH-risk tools return stubs instead of executing
  - task_timeout: (stub, real impl in Step 30's sandbox)

Public API
----------
    from kattappa_runtime.workflow import WorkflowEngine

    engine = WorkflowEngine(
        planner_engine  = planner,
        tool_router     = router,
        dry_run         = False,
        max_steps       = 20,
        max_replans     = 2,
    )

    result = engine.run("Build an RF simulator", domain="rf_systems")
    print(result.execution_log())
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, List, Optional, TYPE_CHECKING

from kattappa_runtime.planner.engine     import PlannerEngine
from kattappa_runtime.planner.schema     import Task, TaskStatus, PlanStatus
from kattappa_runtime.planner.monitor    import PlanMonitor
from kattappa_runtime.workflow.schema    import (
    WorkflowResult, WorkflowEvent, WorkflowStatus, EventType
)
from kattappa_runtime.workflow.router    import ToolRouter

if TYPE_CHECKING:
    from kattappa_runtime.reflection.engine  import ReflectionEngine
    from kattappa_runtime.learning.engine    import LearningEngine
    from kattappa_runtime.tool_mastery.store import ToolMastery

# Default safety caps
_DEFAULT_MAX_STEPS   = 30
_DEFAULT_MAX_REPLANS = 2


class WorkflowEngine:
    """
    Autonomous end-to-end workflow executor.

    Converts a goal string into executed actions, monitoring its own
    progress and replanning autonomously when needed.

    Parameters
    ----------
    planner_engine : PlannerEngine
        The planner that decomposes goals into task plans.
    tool_router : ToolRouter
        Maps task.tool_hint → callable. Register custom tools here.
    dry_run : bool
        If True, HIGH-risk tasks execute as safe stubs.
    max_steps : int
        Hard cap on total task executions per run (safety limit).
    max_replans : int
        Maximum allowed mid-run replan cycles.
    on_task_start : callable | None
        Optional hook: called before each task executes.
        Signature: (task: Task) -> None
    on_task_done : callable | None
        Optional hook: called after each task completes.
        Signature: (task: Task, result: str) -> None
    """

    def __init__(
        self,
        planner_engine:  PlannerEngine,
        tool_router:     Optional[ToolRouter]     = None,
        dry_run:         bool                     = False,
        max_steps:       int                      = _DEFAULT_MAX_STEPS,
        max_replans:     int                      = _DEFAULT_MAX_REPLANS,
        on_task_start:   Optional[Callable]       = None,
        on_task_done:    Optional[Callable]       = None,
    ):
        self.planner     = planner_engine
        self.router      = tool_router or ToolRouter()
        self.dry_run     = dry_run
        self.max_steps   = max_steps
        self.max_replans = max_replans
        self._on_start   = on_task_start
        self._on_done    = on_task_done
        self._monitor    = PlanMonitor()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        goal_title:  str,
        description: str = "",
        domain:      str = "general",
        notes:       str = "",
    ) -> WorkflowResult:
        """
        Execute a goal end-to-end autonomously.

        Parameters
        ----------
        goal_title : str
            Human-readable goal. e.g. "Research impedance matching"
        description : str
            Optional longer context.
        domain : str
            Skill domain for reflection/learning classification.
        notes : str
            Extra context passed through to planner.

        Returns
        -------
        WorkflowResult
            Full execution trace including status, task counts, and log.
        """
        result = WorkflowResult(goal_title=goal_title, domain=domain)

        # --- Submit goal to planner ---
        goal = self.planner.submit(
            title=goal_title, description=description,
            domain=domain, notes=notes,
        )
        result.goal_id = goal.goal_id

        self._log(result, EventType.GOAL_SUBMITTED,
                  message=f"Goal submitted: '{goal_title}' [{domain}]")

        # --- Activate best plan ---
        plan = self.planner.activate(goal.goal_id)
        if not plan:
            return self._finish(result, WorkflowStatus.FAILED,
                                "No plan could be activated.")

        self._log(result, EventType.PLAN_ACTIVATED,
                  message=f"Plan activated: '{plan.title}' ({len(plan.tasks)} tasks)")
        result.tasks_total = len(plan.tasks)

        # --- Autonomous execution loop ---
        step_count   = 0
        replan_count = 0

        while True:
            # Reload goal from store (state may have changed)
            goal = self.planner.store.get_goal(goal.goal_id)
            plan = goal.selected_plan

            if plan is None:
                return self._finish(result, WorkflowStatus.FAILED,
                                    "No selected plan found.")

            # Check if complete
            if plan.is_complete():
                result.tasks_done   = sum(1 for t in plan.tasks if t.status == TaskStatus.DONE)
                result.tasks_failed = sum(1 for t in plan.tasks if t.status == TaskStatus.FAILED)
                return self._finish(result, WorkflowStatus.COMPLETED,
                                    f"All {len(plan.tasks)} tasks executed.")

            # Safety hard cap
            if step_count >= self.max_steps:
                self._log(result, EventType.SAFETY_HALT,
                          message=f"Safety halt: max_steps={self.max_steps} reached")
                return self._finish(result, WorkflowStatus.STOPPED,
                                    f"Stopped at safety limit ({self.max_steps} steps).")

            # Monitor health
            health = self._monitor.check(plan)

            if health.needs_replan:
                if replan_count >= self.max_replans:
                    self._log(result, EventType.SAFETY_HALT,
                              message=f"Replan limit reached ({self.max_replans}). Stopping.")
                    result.replan_count = replan_count
                    return self._finish(result, WorkflowStatus.FAILED,
                                        "Max replan attempts exhausted.")

                # Trigger replan
                self._log(result, EventType.REPLAN_TRIGGERED,
                          message=f"Replanning: {health.replan_reason}")
                goal = self.planner.replan(goal.goal_id, reason=health.replan_reason)
                if not goal:
                    return self._finish(result, WorkflowStatus.FAILED, "Replan failed.")

                new_plan = self.planner.activate(goal.goal_id,
                                                  plan_id=goal.selected_plan_id)
                if not new_plan:
                    return self._finish(result, WorkflowStatus.FAILED,
                                        "Could not activate replan.")

                replan_count += 1
                result.tasks_total = len(new_plan.tasks)
                self._log(result, EventType.REPLAN_COMPLETED,
                          message=f"New plan: '{new_plan.title}' ({len(new_plan.tasks)} tasks)")
                continue

            # Get next executable tasks
            ready = health.next_tasks
            if not ready:
                # Nothing to execute but plan not complete — likely a state inconsistency
                return self._finish(result, WorkflowStatus.FAILED,
                                    "No ready tasks but plan not complete (possible deadlock).")

            # Execute the first ready task
            task = ready[0]
            self._execute_task(goal.goal_id, plan.plan_id, task, result)
            step_count += 1

        # unreachable but satisfies type checkers
        return result  # pragma: no cover

    def run_goal_id(self, goal_id: str) -> Optional[WorkflowResult]:
        """
        Resume execution of a previously submitted and activated goal.
        Use when you've manually submitted a goal via PlannerEngine.

        Returns None if goal_id is not found.
        """
        goal = self.planner.store.get_goal(goal_id)
        if not goal:
            return None
        # Delegate using the goal's metadata
        return self.run(
            goal_title  = goal.title,
            description = goal.description,
            domain      = goal.domain,
            notes       = goal.notes,
        )

    # ------------------------------------------------------------------
    # Private — task execution
    # ------------------------------------------------------------------

    def _execute_task(
        self,
        goal_id: str,
        plan_id: str,
        task:    Task,
        result:  WorkflowResult,
    ) -> None:
        """Execute one task: mark in-progress → route → mark done/failed."""
        self.planner.mark_task_in_progress(goal_id, plan_id, task.task_id)

        self._log(result, EventType.TASK_STARTED,
                  task_title=task.title,
                  tool_hint=task.tool_hint,
                  message=f"Executing: {task.title} [{task.tool_hint or 'default'}]")

        if self._on_start:
            try:
                self._on_start(task)
            except Exception:
                pass

        # Execute via router
        succeeded, output = self.router.execute(task, dry_run=self.dry_run)

        if succeeded:
            self.planner.mark_task_done(goal_id, plan_id, task.task_id, result=output)
            result.tasks_done += 1
            self._log(result, EventType.TASK_COMPLETED,
                      task_title=task.title,
                      tool_hint=task.tool_hint,
                      message=f"Done: {task.title}",
                      result_text=output[:80])
            if self._on_done:
                try:
                    self._on_done(task, output)
                except Exception:
                    pass
        else:
            self.planner.mark_task_failed(goal_id, plan_id, task.task_id, error=output)
            result.tasks_failed += 1
            self._log(result, EventType.TASK_FAILED,
                      task_title=task.title,
                      tool_hint=task.tool_hint,
                      message=f"Failed: {task.title}",
                      result_text=output[:80])

    # ------------------------------------------------------------------
    # Private — logging + finalization
    # ------------------------------------------------------------------

    def _log(
        self,
        result:      WorkflowResult,
        event_type:  EventType,
        message:     str     = "",
        task_title:  str     = "",
        tool_hint:   str     = "",
        result_text: str     = "",
    ) -> None:
        result.events.append(WorkflowEvent(
            event_type = event_type,
            message    = message,
            task_title = task_title,
            tool_hint  = tool_hint,
            result     = result_text,
        ))

    def _finish(
        self,
        result:  WorkflowResult,
        status:  WorkflowStatus,
        summary: str,
    ) -> WorkflowResult:
        result.status       = status
        result.summary      = summary
        result.completed_at = datetime.now(timezone.utc).isoformat()
        self._log(result, EventType.WORKFLOW_DONE,
                  message=f"Workflow {status.value}: {summary}")
        return result
