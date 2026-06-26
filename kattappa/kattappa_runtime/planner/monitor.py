"""
Plan Monitor — tracks execution progress and detects re-plan conditions.

The Monitor watches a Plan's Tasks and:
  1. Emits a summary of current progress
  2. Detects when a plan needs re-planning (too many failures, stalled)
  3. Determines which tasks are ready to execute next
  4. Calculates overall health score

This is purely analytical — it doesn't execute tasks, it only observes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from kattappa_runtime.planner.schema import Plan, Task, TaskStatus, RiskLevel


@dataclass
class PlanHealth:
    """Snapshot of a Plan's execution health at one point in time."""
    plan_id:            str
    plan_title:         str
    progress_pct:       float
    ready_count:        int
    pending_count:      int
    done_count:         int
    failed_count:       int
    total_count:        int
    health_score:       float   # 0.0 (catastrophic) → 1.0 (perfect)
    needs_replan:       bool
    replan_reason:      str
    next_tasks:         List[Task]

    def summary(self) -> str:
        """One-line human-readable progress summary."""
        bar_filled = int(self.progress_pct / 10)
        bar        = "█" * bar_filled + "░" * (10 - bar_filled)
        return (
            f"[{bar}] {self.progress_pct:5.1f}%  "
            f"done={self.done_count}  failed={self.failed_count}  "
            f"ready={self.ready_count}  pending={self.pending_count}  "
            f"health={self.health_score:.2f}"
            + (f"  ⚠ REPLAN: {self.replan_reason}" if self.needs_replan else "")
        )


# Thresholds for re-plan detection
_MAX_FAILURE_RATE    = 0.40  # >40% tasks failed → replan
_MAX_CRITICAL_FAILS  = 1     # any critical-risk failure → replan immediately


class PlanMonitor:
    """
    Analyses a Plan's current state and determines next actions.

    Usage
    -----
        monitor = PlanMonitor()
        health  = monitor.check(plan)
        print(health.summary())

        if health.needs_replan:
            # Trigger PlannerEngine.replan(goal)
            pass
        else:
            for task in health.next_tasks:
                executor.run(task)
    """

    def check(self, plan: Plan) -> PlanHealth:
        """
        Produce a PlanHealth snapshot for the current plan state.

        Parameters
        ----------
        plan : Plan
            The plan being executed.

        Returns
        -------
        PlanHealth
            Full health report including next ready tasks and replan flag.
        """
        total   = len(plan.tasks)
        done    = sum(1 for t in plan.tasks if t.status == TaskStatus.DONE)
        failed  = sum(1 for t in plan.tasks if t.status == TaskStatus.FAILED)
        skipped = sum(1 for t in plan.tasks if t.status == TaskStatus.SKIPPED)
        pending = sum(1 for t in plan.tasks if t.status == TaskStatus.PENDING)

        progress_pct = plan.progress_pct()

        # Ready tasks: pending with all dependencies done
        next_tasks = plan.ready_tasks()

        # Compute health score
        health_score = self._health_score(total, done, failed, skipped)

        # Replan detection
        needs_replan, reason = self._check_replan(plan, total, failed)

        return PlanHealth(
            plan_id       = plan.plan_id,
            plan_title    = plan.title,
            progress_pct  = progress_pct,
            ready_count   = len(next_tasks),
            pending_count = pending,
            done_count    = done,
            failed_count  = failed,
            total_count   = total,
            health_score  = health_score,
            needs_replan  = needs_replan,
            replan_reason = reason,
            next_tasks    = next_tasks,
        )

    def full_report(self, plan: Plan) -> str:
        """
        Multi-line progress report for a Plan.

        Example:
            Plan: Thorough — full task sequence  [Step 3/6]
            Progress: [███░░░░░░░] 50.0%  health=0.83

            ✅ DONE     Search Wikipedia for overview
            ✅ DONE     Search Arxiv for technical papers
            ⏳ RUNNING  Search local corpus for prior knowledge
            🔲 PENDING  Synthesise findings into key facts
            🔲 PENDING  Store findings in semantic memory
            🔲 PENDING  Update skill profile for domain
        """
        health = self.check(plan)
        lines  = [
            f"Plan: {plan.title}",
            f"Progress: {health.summary()}",
            "",
        ]

        _STATUS_ICON = {
            TaskStatus.PENDING:     "🔲 PENDING ",
            TaskStatus.IN_PROGRESS: "⏳ RUNNING ",
            TaskStatus.DONE:        "✅ DONE    ",
            TaskStatus.FAILED:      "❌ FAILED  ",
            TaskStatus.SKIPPED:     "⏭  SKIPPED ",
        }

        for task in plan.tasks:
            icon = _STATUS_ICON.get(task.status, "?? ")
            line = f"  {icon} {task.title}"
            if task.status == TaskStatus.FAILED and task.error:
                line += f"  [error: {task.error[:60]}]"
            lines.append(line)

        if health.needs_replan:
            lines.append(f"\n  ⚠  Re-plan recommended: {health.replan_reason}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _health_score(total: int, done: int, failed: int, skipped: int) -> float:
        """
        Composite health score in [0.0, 1.0].
        Perfect = all tasks done, no failures.
        Catastrophic = all tasks failed.
        """
        if total == 0:
            return 1.0
        completion = (done + skipped) / total
        failure_penalty = failed / total
        return round(max(0.0, completion - failure_penalty * 2), 3)

    @staticmethod
    def _check_replan(plan: Plan, total: int, failed: int) -> tuple[bool, str]:
        """Determine if re-planning is needed and why."""
        if total == 0:
            return False, ""

        # Too many failures
        fail_rate = failed / total
        if fail_rate > _MAX_FAILURE_RATE:
            return True, f"{fail_rate*100:.0f}% of tasks failed (threshold: {_MAX_FAILURE_RATE*100:.0f}%)"

        # Any critical-risk task failed
        critical_fails = [
            t for t in plan.tasks
            if t.status == TaskStatus.FAILED and t.risk_level == RiskLevel.CRITICAL
        ]
        if len(critical_fails) >= _MAX_CRITICAL_FAILS:
            titles = ", ".join(t.title[:30] for t in critical_fails[:2])
            return True, f"Critical-risk task failed: {titles}"

        # Deadlocked: pending tasks exist but none are ready
        pending = [t for t in plan.tasks if t.status == TaskStatus.PENDING]
        ready   = plan.ready_tasks()
        if pending and not ready:
            return True, "Deadlock detected: pending tasks with no executable next step"

        return False, ""
