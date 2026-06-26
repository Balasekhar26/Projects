"""
Planner Engine — Step 27 Core
==============================

The PlannerEngine is Kattappa's "mini project manager."

It implements the full planning loop:

    Goal
      ↓ decompose()
    Plan alternative A  ←  fast
    Plan alternative B  ←  thorough
      ↓ select_plan()     (lowest plan_score wins)
    Active Plan
      ↓ start()
    Monitor Loop:
      ↓ check health     (PlanMonitor)
      ↓ get_ready_tasks()
      ↓ mark_task_done()/mark_task_failed()
      ↓ if needs_replan → replan()
      ↓ if all done → complete()

Integration with cognitive stack:
  - After plan completes: ReflectionEngine.reflect() on the outcome
  - After reflection: LearningEngine.learn_from() to extract lessons
  - ToolMastery.record_use() for each tool_hint executed

Public API
----------
    from kattappa_runtime.planner import PlannerEngine

    planner = PlannerEngine(
        memory=memory,
        reflection_engine=reflection_engine,
        learning_engine=learning_engine,
        tool_mastery=tool_mastery,
    )

    goal   = planner.submit("Research impedance matching", domain="rf_systems")
    plan   = goal.selected_plan

    health = planner.status(goal.goal_id)
    print(health.summary())

    planner.mark_task_done(goal.goal_id, plan.plan_id, plan.tasks[0].task_id,
                           result="Found 3 Wikipedia articles")

    if health.needs_replan:
        goal = planner.replan(goal.goal_id, reason=health.replan_reason)
"""

from __future__ import annotations

from typing import Callable, List, Optional, TYPE_CHECKING

from kattappa_runtime.planner.schema     import Goal, Plan, Task, TaskStatus, PlanStatus
from kattappa_runtime.planner.store      import PlannerStore
from kattappa_runtime.planner.decomposer import GoalDecomposer
from kattappa_runtime.planner.monitor    import PlanMonitor, PlanHealth

if TYPE_CHECKING:
    from kattappa_runtime.memory            import MemoryProvider
    from kattappa_runtime.reflection.engine import ReflectionEngine
    from kattappa_runtime.learning.engine   import LearningEngine
    from kattappa_runtime.tool_mastery.store import ToolMastery


class PlannerEngine:
    """
    Goal-to-execution planning engine.

    Parameters
    ----------
    memory : MemoryProvider | None
        Runtime memory for storing plan outcomes.
    reflection_engine : ReflectionEngine | None
        If provided, reflects on plan completion.
    learning_engine : LearningEngine | None
        If provided, learns from reflection after plan completion.
    tool_mastery : ToolMastery | None
        If provided, records tool use on task completion.
    store : PlannerStore | None
        Custom store for testing.
    llm_decomposer : callable | None
        LLM hook for richer goal decomposition.
    """

    def __init__(
        self,
        memory:            Optional["MemoryProvider"]    = None,
        reflection_engine: Optional["ReflectionEngine"] = None,
        learning_engine:   Optional["LearningEngine"]   = None,
        tool_mastery:      Optional["ToolMastery"]       = None,
        store:             Optional[PlannerStore]        = None,
        llm_decomposer:    Optional[Callable]            = None,
    ):
        self.memory     = memory
        self.reflection = reflection_engine
        self.learning   = learning_engine
        self.tool_mast  = tool_mastery
        self.store      = store or PlannerStore()
        self.decomposer = GoalDecomposer(llm_decomposer=llm_decomposer)
        self.monitor    = PlanMonitor()

    # ------------------------------------------------------------------
    # Public — lifecycle
    # ------------------------------------------------------------------

    def submit(
        self,
        title:       str,
        description: str = "",
        domain:      str = "general",
        notes:       str = "",
    ) -> Goal:
        """
        Submit a new goal. Decomposes it into plans and persists.

        Returns
        -------
        Goal
            With two plan alternatives attached and best plan pre-selected.
        """
        goal = Goal(
            title       = title,
            description = description or title,
            domain      = domain,
            notes       = notes,
        )
        # Decompose into plans
        goal = self.decomposer.decompose(goal)

        # Persist
        self.store.save_goal(goal)

        return goal

    def activate(self, goal_id: str, plan_id: Optional[str] = None) -> Optional[Plan]:
        """
        Activate a plan for execution. If plan_id is None, uses the
        pre-selected best plan.

        Returns the activated Plan, or None if goal/plan not found.
        """
        goal = self.store.get_goal(goal_id)
        if not goal:
            return None

        target_plan_id = plan_id or goal.selected_plan_id
        if not target_plan_id and goal.plans:
            target_plan_id = goal.plans[0].plan_id

        if not target_plan_id:
            return None

        return self.store.activate_plan(goal_id, target_plan_id)

    def mark_task_done(
        self,
        goal_id:  str,
        plan_id:  str,
        task_id:  str,
        result:   str = "",
    ) -> Optional[Task]:
        """Mark one task as DONE. Records tool use in ToolMastery if applicable."""
        goal = self.store.get_goal(goal_id)
        task = self._find_task(goal, plan_id, task_id)
        updated = self.store.update_task(goal_id, plan_id, task_id,
                                         TaskStatus.DONE, result=result)

        # Record tool use
        if updated and task and task.tool_hint and self.tool_mast:
            try:
                self.tool_mast.record_use(task.tool_hint, succeeded=True)
            except Exception:
                pass

        # Check if plan is now complete
        goal = self.store.get_goal(goal_id)
        if goal:
            plan = self._find_plan(goal, plan_id)
            if plan and plan.is_complete():
                self._on_plan_complete(goal, plan)

        return updated

    def mark_task_failed(
        self,
        goal_id:  str,
        plan_id:  str,
        task_id:  str,
        error:    str = "",
    ) -> Optional[Task]:
        """Mark one task as FAILED. Records tool failure in ToolMastery."""
        goal = self.store.get_goal(goal_id)
        task = self._find_task(goal, plan_id, task_id)
        updated = self.store.update_task(goal_id, plan_id, task_id,
                                         TaskStatus.FAILED, error=error)

        # Record tool failure
        if updated and task and task.tool_hint and self.tool_mast:
            try:
                self.tool_mast.record_use(task.tool_hint, succeeded=False,
                                           failure_note=error[:100])
            except Exception:
                pass

        return updated

    def mark_task_in_progress(
        self,
        goal_id:  str,
        plan_id:  str,
        task_id:  str,
    ) -> Optional[Task]:
        """Mark one task as IN_PROGRESS."""
        return self.store.update_task(goal_id, plan_id, task_id,
                                       TaskStatus.IN_PROGRESS)

    def replan(self, goal_id: str, reason: str = "") -> Optional[Goal]:
        """
        Abandon the current active plan and generate fresh plans.
        Preserves completed task results in notes.

        Returns
        -------
        Goal
            With new plans generated. Caller must call activate() again.
        """
        goal = self.store.get_goal(goal_id)
        if not goal:
            return None

        # Abandon all active plans
        for plan in goal.plans:
            if plan.status == PlanStatus.ACTIVE:
                self.store.fail_plan(goal_id, plan.plan_id)

        # Generate fresh plans
        goal = self.store.get_goal(goal_id)
        fresh_goal = Goal(
            goal_id     = goal.goal_id,
            title       = goal.title,
            description = goal.description,
            domain      = goal.domain,
            notes       = f"{goal.notes} | Replan: {reason}".strip(" |"),
            created_at  = goal.created_at,
        )
        fresh_goal = self.decomposer.decompose(fresh_goal)

        # Merge new plans into existing goal
        goal = self.store.get_goal(goal_id)
        goal.plans.extend(fresh_goal.plans)
        goal.selected_plan_id = fresh_goal.selected_plan_id
        self.store.save_goal(goal)

        return goal

    # ------------------------------------------------------------------
    # Public — queries
    # ------------------------------------------------------------------

    def status(self, goal_id: str) -> Optional[PlanHealth]:
        """Check current health of a goal's active plan."""
        goal = self.store.get_goal(goal_id)
        if not goal:
            return None
        plan = goal.selected_plan
        if not plan:
            return None
        return self.monitor.check(plan)

    def progress_report(self, goal_id: str) -> str:
        """Human-readable multi-line progress report."""
        goal = self.store.get_goal(goal_id)
        if not goal:
            return f"Goal {goal_id} not found."
        plan = goal.selected_plan
        if not plan:
            return f"Goal '{goal.title}' has no selected plan."
        header = f"Goal: {goal.title}  [domain={goal.domain}]\n"
        return header + self.monitor.full_report(plan)

    def get_ready_tasks(self, goal_id: str) -> List[Task]:
        """Return tasks that are ready to execute right now."""
        goal = self.store.get_goal(goal_id)
        if not goal or not goal.selected_plan:
            return []
        return goal.selected_plan.ready_tasks()

    def all_goals(self) -> List[Goal]:
        return self.store.get_all()

    def active_goals(self) -> List[Goal]:
        return self.store.get_active()

    # ------------------------------------------------------------------
    # Private — event handlers
    # ------------------------------------------------------------------

    def _on_plan_complete(self, goal: Goal, plan: Plan) -> None:
        """Called when all tasks in a plan are done/skipped."""
        self.store.complete_plan(goal.goal_id, plan.plan_id)

        # Log episode to memory
        if self.memory:
            try:
                self.memory.writer.store_episode(
                    event=(
                        f"[Planner] Completed plan '{plan.title}' "
                        f"for goal '{goal.title}' "
                        f"in domain={goal.domain}. "
                        f"{len(plan.tasks)} tasks executed."
                    ),
                    importance = 0.8,
                    confidence = 0.9,
                )
            except Exception:
                pass

        # Reflect on the plan execution
        if self.reflection:
            try:
                succeeded = not plan.has_critical_failure()
                reflection = self.reflection.reflect(
                    input_text   = f"Plan: {goal.title}",
                    action_taken = f"Executed {len(plan.tasks)}-task plan",
                    result       = f"Plan {'completed' if succeeded else 'completed with failures'}. "
                                   f"Tasks: {len(plan.tasks)}, "
                                   f"Failed: {sum(1 for t in plan.tasks if t.status == TaskStatus.FAILED)}",
                    domain       = goal.domain,
                    succeeded    = succeeded,
                    partial      = plan.has_critical_failure(),
                    notes        = f"goal_id={goal.goal_id}",
                )
                if self.learning:
                    self.learning.learn_from(reflection)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Private — helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_plan(goal: Goal, plan_id: str) -> Optional[Plan]:
        for p in goal.plans:
            if p.plan_id == plan_id:
                return p
        return None

    @staticmethod
    def _find_task(goal: Optional[Goal], plan_id: str, task_id: str) -> Optional[Task]:
        if not goal:
            return None
        for p in goal.plans:
            if p.plan_id == plan_id:
                for t in p.tasks:
                    if t.task_id == task_id:
                        return t
        return None
