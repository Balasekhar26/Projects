"""
Tests for Step 27 — Planner Evolution
========================================

All tests are hermetic (no network, no training, disk in tmp_path).

Covers:

Schema
  - Task: is_ready, risk_score, serialisation roundtrip
  - Plan: total_cost, max_risk, plan_score, ready_tasks (topology),
    is_complete, has_critical_failure, progress_pct, serialisation
  - Goal: best_plan selection (lowest score), selected_plan accessor,
    serialisation roundtrip

PlannerStore
  - save_goal, get_goal, get_all, count
  - update_task: status/result/timestamps propagate correctly
  - activate_plan: sets status ACTIVE, updates selected_plan_id
  - complete_plan / fail_plan
  - persistence across instances

GoalDecomposer
  - Research keyword triggers correct template
  - Build keyword triggers correct template
  - Debug keyword triggers correct template
  - Generic fallback for unknown goal
  - Produces exactly two plans (fast + thorough)
  - Fast plan has ≤3 tasks; thorough has more
  - Tasks have linear dependency chain
  - LLM decomposer hook is used when provided
  - LLM decomposer fallback on error

PlanMonitor
  - progress_pct tracks done/skipped tasks
  - health_score = 1.0 when all done
  - health_score reduced by failures
  - ready_tasks only returns tasks with satisfied deps
  - needs_replan when failure_rate > threshold
  - needs_replan on critical-risk failure
  - needs_replan on deadlock (pending tasks, none ready)
  - full_report returns non-empty string

PlannerEngine Integration
  - submit() creates goal with 2 plans, stores it
  - activate() marks plan ACTIVE
  - get_ready_tasks() returns first task (no deps)
  - mark_task_done() updates status, stores result
  - mark_task_done() fires _on_plan_complete() when all done
  - mark_task_failed() updates status, stores error
  - ToolMastery.record_use() called on task done/failed
  - ReflectionEngine.reflect() called on plan complete
  - LearningEngine.learn_from() called on plan complete
  - memory.writer.store_episode() called on plan complete
  - progress_report() returns non-empty string
  - status() returns PlanHealth
  - replan() generates new plan alternatives, preserves history
  - Works without optional dependencies (reflection/learning/memory)
"""

import pytest
from unittest.mock import MagicMock, patch
from kattappa_runtime.planner.schema     import (
    Task, Plan, Goal, TaskStatus, RiskLevel, PlanStatus
)
from kattappa_runtime.planner.store      import PlannerStore
from kattappa_runtime.planner.decomposer import GoalDecomposer
from kattappa_runtime.planner.monitor    import PlanMonitor
from kattappa_runtime.planner.engine     import PlannerEngine


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def tmp_store(tmp_path):
    return PlannerStore(path=str(tmp_path / "goals.jsonl"))


@pytest.fixture
def mock_memory():
    m = MagicMock()
    m.writer = MagicMock()
    m.writer.store_episode = MagicMock()
    return m


@pytest.fixture
def mock_reflection():
    from kattappa_runtime.reflection.schema import Reflection, OutcomeLabel
    eng = MagicMock()
    eng.reflect.return_value = Reflection(
        domain="test", outcome=OutcomeLabel.SUCCESS,
        lesson="plan worked", confidence_delta=0.05,
    )
    return eng


@pytest.fixture
def mock_learning():
    from kattappa_runtime.learning.schema import LearningRecord
    eng = MagicMock()
    eng.learn_from.return_value = LearningRecord(domain="test")
    return eng


@pytest.fixture
def mock_tool_mastery():
    return MagicMock()


def make_simple_plan(goal_id="g1", n_tasks=3, with_critical=False) -> Plan:
    """Helper: plan with n linear tasks."""
    tasks = []
    for i in range(n_tasks):
        risk = RiskLevel.CRITICAL if (with_critical and i == 1) else RiskLevel.LOW
        t = Task(
            title=f"Task {i+1}", description=f"Do step {i+1}",
            tool_hint="code_runner", estimated_cost=1.0, risk_level=risk,
            dependencies=[tasks[i-1].task_id] if i > 0 else [],
        )
        tasks.append(t)
    return Plan(goal_id=goal_id, title="Test Plan", tasks=tasks)


def make_engine(tmp_path, memory=None, reflection=None, learning=None, tool_mastery=None):
    store = PlannerStore(path=str(tmp_path / "goals.jsonl"))
    return PlannerEngine(
        memory=memory,
        reflection_engine=reflection,
        learning_engine=learning,
        tool_mastery=tool_mastery,
        store=store,
    )


# ===========================================================================
# Schema — Task
# ===========================================================================

class TestTaskSchema:
    def test_risk_score_low(self):
        t = Task(risk_level=RiskLevel.LOW)
        assert t.risk_score == 1.0

    def test_risk_score_critical(self):
        t = Task(risk_level=RiskLevel.CRITICAL)
        assert t.risk_score == 5.0

    def test_serialisation_roundtrip(self):
        t = Task(title="Do something", tool_hint="git",
                 estimated_cost=2.5, risk_level=RiskLevel.MEDIUM,
                 dependencies=["abc", "def"])
        d  = t.to_dict()
        t2 = Task.from_dict(d)
        assert t2.title          == "Do something"
        assert t2.risk_level     == RiskLevel.MEDIUM
        assert t2.dependencies   == ["abc", "def"]
        assert t2.estimated_cost == pytest.approx(2.5)

    def test_default_status_pending(self):
        t = Task()
        assert t.status == TaskStatus.PENDING


# ===========================================================================
# Schema — Plan
# ===========================================================================

class TestPlanSchema:
    def test_total_cost(self):
        plan = make_simple_plan(n_tasks=3)
        assert plan.total_cost == pytest.approx(3.0)

    def test_max_risk_low(self):
        plan = make_simple_plan(n_tasks=3)
        assert plan.max_risk == RiskLevel.LOW

    def test_max_risk_critical(self):
        plan = make_simple_plan(n_tasks=3, with_critical=True)
        assert plan.max_risk == RiskLevel.CRITICAL

    def test_plan_score_lower_for_safe_plan(self):
        safe_plan    = make_simple_plan(n_tasks=3)
        risky_plan   = make_simple_plan(n_tasks=3, with_critical=True)
        assert safe_plan.plan_score < risky_plan.plan_score

    def test_ready_tasks_first_only(self):
        plan = make_simple_plan(n_tasks=3)
        ready = plan.ready_tasks()
        assert len(ready) == 1
        assert ready[0].title == "Task 1"

    def test_ready_tasks_after_first_done(self):
        plan = make_simple_plan(n_tasks=3)
        plan.tasks[0].status = TaskStatus.DONE
        ready = plan.ready_tasks()
        assert len(ready) == 1
        assert ready[0].title == "Task 2"

    def test_progress_pct_zero_at_start(self):
        plan = make_simple_plan(n_tasks=4)
        assert plan.progress_pct() == pytest.approx(0.0)

    def test_progress_pct_partial(self):
        plan = make_simple_plan(n_tasks=4)
        plan.tasks[0].status = TaskStatus.DONE
        plan.tasks[1].status = TaskStatus.DONE
        assert plan.progress_pct() == pytest.approx(50.0)

    def test_is_complete_all_done(self):
        plan = make_simple_plan(n_tasks=2)
        for t in plan.tasks:
            t.status = TaskStatus.DONE
        assert plan.is_complete() is True

    def test_is_complete_with_skipped(self):
        plan = make_simple_plan(n_tasks=2)
        plan.tasks[0].status = TaskStatus.DONE
        plan.tasks[1].status = TaskStatus.SKIPPED
        assert plan.is_complete() is True

    def test_is_complete_false_when_pending(self):
        plan = make_simple_plan(n_tasks=2)
        plan.tasks[0].status = TaskStatus.DONE
        assert plan.is_complete() is False

    def test_has_critical_failure_true(self):
        plan = make_simple_plan(n_tasks=3, with_critical=True)
        plan.tasks[1].status = TaskStatus.FAILED
        assert plan.has_critical_failure() is True

    def test_has_critical_failure_false(self):
        plan = make_simple_plan(n_tasks=3)
        plan.tasks[0].status = TaskStatus.FAILED
        assert plan.has_critical_failure() is False

    def test_serialisation_roundtrip(self):
        plan = make_simple_plan(n_tasks=3)
        d    = plan.to_dict()
        p2   = Plan.from_dict(d)
        assert p2.title == "Test Plan"
        assert len(p2.tasks) == 3
        assert p2.tasks[1].dependencies[0] == plan.tasks[0].task_id


# ===========================================================================
# Schema — Goal
# ===========================================================================

class TestGoalSchema:
    def test_best_plan_is_lowest_score(self):
        goal     = Goal(title="t")
        safe     = make_simple_plan(goal_id=goal.goal_id, n_tasks=2)
        risky    = make_simple_plan(goal_id=goal.goal_id, n_tasks=2, with_critical=True)
        goal.plans = [risky, safe]
        best = goal.best_plan()
        assert best.plan_id == safe.plan_id

    def test_selected_plan_returns_matching_plan(self):
        goal     = Goal(title="t")
        plan     = make_simple_plan(goal_id=goal.goal_id)
        goal.plans           = [plan]
        goal.selected_plan_id = plan.plan_id
        assert goal.selected_plan.plan_id == plan.plan_id

    def test_serialisation_roundtrip(self):
        goal  = Goal(title="Build RF simulator", domain="rf_systems")
        plan  = make_simple_plan(goal_id=goal.goal_id, n_tasks=2)
        goal.plans           = [plan]
        goal.selected_plan_id = plan.plan_id
        d     = goal.to_dict()
        g2    = Goal.from_dict(d)
        assert g2.title   == "Build RF simulator"
        assert g2.domain  == "rf_systems"
        assert len(g2.plans) == 1
        assert len(g2.plans[0].tasks) == 2


# ===========================================================================
# PlannerStore
# ===========================================================================

class TestPlannerStore:
    def test_save_and_get(self, tmp_store):
        goal = Goal(title="t")
        plan = make_simple_plan(goal_id=goal.goal_id, n_tasks=2)
        goal.plans = [plan]
        tmp_store.save_goal(goal)
        loaded = tmp_store.get_goal(goal.goal_id)
        assert loaded is not None
        assert loaded.title == "t"

    def test_count(self, tmp_store):
        for i in range(3):
            goal = Goal(title=f"goal {i}")
            tmp_store.save_goal(goal)
        assert tmp_store.count() == 3

    def test_update_task_status(self, tmp_store):
        goal = Goal(title="t")
        plan = make_simple_plan(goal_id=goal.goal_id, n_tasks=2)
        goal.plans = [plan]
        tmp_store.save_goal(goal)

        task = plan.tasks[0]
        updated = tmp_store.update_task(
            goal.goal_id, plan.plan_id, task.task_id,
            TaskStatus.DONE, result="done!"
        )
        assert updated.status == TaskStatus.DONE
        assert updated.result == "done!"
        assert updated.completed_at != ""

    def test_update_task_in_progress_sets_started_at(self, tmp_store):
        goal = Goal(title="t")
        plan = make_simple_plan(goal_id=goal.goal_id)
        goal.plans = [plan]
        tmp_store.save_goal(goal)
        task = plan.tasks[0]
        updated = tmp_store.update_task(
            goal.goal_id, plan.plan_id, task.task_id, TaskStatus.IN_PROGRESS
        )
        assert updated.started_at != ""

    def test_activate_plan(self, tmp_store):
        goal = Goal(title="t")
        plan = make_simple_plan(goal_id=goal.goal_id)
        goal.plans = [plan]
        tmp_store.save_goal(goal)
        activated = tmp_store.activate_plan(goal.goal_id, plan.plan_id)
        assert activated.status == PlanStatus.ACTIVE
        loaded = tmp_store.get_goal(goal.goal_id)
        assert loaded.selected_plan_id == plan.plan_id

    def test_get_active(self, tmp_store):
        goal = Goal(title="t")
        plan = make_simple_plan(goal_id=goal.goal_id)
        goal.plans = [plan]
        tmp_store.save_goal(goal)
        assert len(tmp_store.get_active()) == 0
        tmp_store.activate_plan(goal.goal_id, plan.plan_id)
        assert len(tmp_store.get_active()) == 1

    def test_persistence_across_instances(self, tmp_path):
        path = str(tmp_path / "g.jsonl")
        s1   = PlannerStore(path=path)
        goal = Goal(title="persist me")
        plan = make_simple_plan(goal_id=goal.goal_id, n_tasks=2)
        goal.plans = [plan]
        s1.save_goal(goal)

        s2 = PlannerStore(path=path)
        assert s2.count() == 1
        loaded = s2.get_goal(goal.goal_id)
        assert len(loaded.plans[0].tasks) == 2

    def test_unknown_goal_update_returns_none(self, tmp_store):
        result = tmp_store.update_task("bad-id", "bad-pid", "bad-tid", TaskStatus.DONE)
        assert result is None


# ===========================================================================
# GoalDecomposer
# ===========================================================================

class TestGoalDecomposer:
    def _decompose(self, title: str, desc: str = "") -> Goal:
        d    = GoalDecomposer()
        goal = Goal(title=title, description=desc or title)
        return d.decompose(goal)

    def test_produces_two_plans(self):
        goal = self._decompose("Research neural networks")
        assert len(goal.plans) == 2

    def test_fast_plan_has_three_or_fewer_tasks(self):
        goal = self._decompose("Research neural networks")
        fast = min(goal.plans, key=lambda p: len(p.tasks))
        assert len(fast.tasks) <= 3

    def test_thorough_plan_has_more_tasks(self):
        goal = self._decompose("Research neural networks")
        fast     = min(goal.plans, key=lambda p: len(p.tasks))
        thorough = max(goal.plans, key=lambda p: len(p.tasks))
        assert len(thorough.tasks) > len(fast.tasks)

    def test_research_keyword_triggers_research_template(self):
        goal  = self._decompose("Research impedance matching")
        tasks = max(goal.plans, key=lambda p: len(p.tasks)).tasks
        titles = [t.title for t in tasks]
        assert any("Wikipedia" in t or "research" in t.lower() for t in titles)

    def test_build_keyword_triggers_build_template(self):
        goal  = self._decompose("Build an RF simulator")
        tasks = max(goal.plans, key=lambda p: len(p.tasks)).tasks
        titles = [t.title for t in tasks]
        assert any("code" in t.lower() or "implement" in t.lower() or "test" in t.lower()
                   for t in titles)

    def test_debug_keyword_triggers_debug_template(self):
        goal  = self._decompose("Debug the tokenizer failure")
        tasks = max(goal.plans, key=lambda p: len(p.tasks)).tasks
        titles = [t.title for t in tasks]
        assert any("reproduce" in t.lower() or "fix" in t.lower() for t in titles)

    def test_unknown_goal_uses_generic_template(self):
        goal  = self._decompose("Contemplate the universe")
        # Generic template should produce tasks
        assert any(len(p.tasks) >= 3 for p in goal.plans)

    def test_tasks_have_linear_dependencies(self):
        goal  = self._decompose("Research impedance matching")
        plan  = max(goal.plans, key=lambda p: len(p.tasks))
        # Task 0 has no deps; Task 1 depends on Task 0; etc.
        assert plan.tasks[0].dependencies == []
        assert plan.tasks[1].dependencies == [plan.tasks[0].task_id]

    def test_best_plan_selected_on_decompose(self):
        goal = self._decompose("Build an RF simulator")
        assert goal.selected_plan_id != ""
        assert goal.selected_plan is not None

    def test_llm_decomposer_hook_used(self):
        def my_llm(title, desc):
            return [
                {"title": "Custom task 1", "description": "desc", "tool_hint": "git",
                 "estimated_cost": 1.0, "risk_level": "low"},
                {"title": "Custom task 2", "description": "desc", "tool_hint": "git",
                 "estimated_cost": 2.0, "risk_level": "medium"},
            ]

        d    = GoalDecomposer(llm_decomposer=my_llm)
        goal = Goal(title="Do something")
        goal = d.decompose(goal)
        # The thorough plan should use the LLM output
        task_titles = [t.title for p in goal.plans for t in p.tasks]
        assert any("Custom task" in t for t in task_titles)

    def test_llm_decomposer_fallback_on_error(self):
        def bad_llm(title, desc):
            raise RuntimeError("LLM down")

        d    = GoalDecomposer(llm_decomposer=bad_llm)
        goal = Goal(title="Research something")
        goal = d.decompose(goal)
        # Should fall back to rule-based — still produces plans
        assert len(goal.plans) == 2


# ===========================================================================
# PlanMonitor
# ===========================================================================

class TestPlanMonitor:
    def test_health_score_all_done(self):
        plan = make_simple_plan(n_tasks=3)
        for t in plan.tasks:
            t.status = TaskStatus.DONE
        h = PlanMonitor().check(plan)
        assert h.health_score == pytest.approx(1.0)

    def test_health_score_reduced_by_failure(self):
        plan = make_simple_plan(n_tasks=4)
        plan.tasks[0].status = TaskStatus.DONE
        plan.tasks[1].status = TaskStatus.FAILED
        h = PlanMonitor().check(plan)
        assert h.health_score < 0.5

    def test_progress_pct_tracked(self):
        plan = make_simple_plan(n_tasks=4)
        plan.tasks[0].status = TaskStatus.DONE
        plan.tasks[1].status = TaskStatus.DONE
        h = PlanMonitor().check(plan)
        assert h.progress_pct == pytest.approx(50.0)

    def test_ready_tasks_count(self):
        plan = make_simple_plan(n_tasks=3)
        h    = PlanMonitor().check(plan)
        assert h.ready_count == 1

    def test_ready_tasks_after_first_done(self):
        plan = make_simple_plan(n_tasks=3)
        plan.tasks[0].status = TaskStatus.DONE
        h = PlanMonitor().check(plan)
        assert h.ready_count == 1
        assert h.next_tasks[0].title == "Task 2"

    def test_needs_replan_high_failure_rate(self):
        plan = make_simple_plan(n_tasks=4)
        plan.tasks[0].status = TaskStatus.FAILED
        plan.tasks[1].status = TaskStatus.FAILED
        h = PlanMonitor().check(plan)
        assert h.needs_replan is True
        assert "failed" in h.replan_reason.lower()

    def test_needs_replan_critical_failure(self):
        plan = make_simple_plan(n_tasks=3, with_critical=True)
        plan.tasks[1].status = TaskStatus.FAILED  # task 1 is CRITICAL
        h = PlanMonitor().check(plan)
        assert h.needs_replan is True

    def test_no_replan_needed_when_progressing_normally(self):
        plan = make_simple_plan(n_tasks=4)
        plan.tasks[0].status = TaskStatus.DONE
        h = PlanMonitor().check(plan)
        assert h.needs_replan is False

    def test_full_report_non_empty(self):
        plan = make_simple_plan(n_tasks=3)
        report = PlanMonitor().full_report(plan)
        assert "Test Plan" in report
        assert "Task 1" in report


# ===========================================================================
# PlannerEngine Integration
# ===========================================================================

class TestPlannerEngine:
    def test_submit_creates_goal_with_plans(self, tmp_path, mock_memory):
        eng  = make_engine(tmp_path, memory=mock_memory)
        goal = eng.submit("Research impedance matching", domain="rf_systems")
        assert goal.goal_id
        assert len(goal.plans) == 2
        assert goal.selected_plan_id

    def test_submit_persists_goal(self, tmp_path):
        eng  = make_engine(tmp_path)
        goal = eng.submit("Research impedance matching")
        assert eng.store.get_goal(goal.goal_id) is not None

    def test_activate_marks_plan_active(self, tmp_path):
        eng  = make_engine(tmp_path)
        goal = eng.submit("Build a tool")
        plan = eng.activate(goal.goal_id)
        assert plan is not None
        assert plan.status == PlanStatus.ACTIVE

    def test_get_ready_tasks_returns_first_task(self, tmp_path):
        eng    = make_engine(tmp_path)
        goal   = eng.submit("Debug tokenizer")
        eng.activate(goal.goal_id)
        ready  = eng.get_ready_tasks(goal.goal_id)
        assert len(ready) >= 1

    def test_mark_task_done_updates_status(self, tmp_path):
        eng  = make_engine(tmp_path)
        goal = eng.submit("Research something")
        eng.activate(goal.goal_id)
        plan  = eng.store.get_goal(goal.goal_id).selected_plan
        task  = plan.tasks[0]
        updated = eng.mark_task_done(goal.goal_id, plan.plan_id, task.task_id,
                                     result="All done")
        assert updated.status == TaskStatus.DONE
        assert updated.result == "All done"

    def test_mark_task_failed_updates_status(self, tmp_path):
        eng  = make_engine(tmp_path)
        goal = eng.submit("Research something")
        eng.activate(goal.goal_id)
        plan = eng.store.get_goal(goal.goal_id).selected_plan
        task = plan.tasks[0]
        updated = eng.mark_task_failed(goal.goal_id, plan.plan_id, task.task_id,
                                        error="Network error")
        assert updated.status == TaskStatus.FAILED
        assert "Network error" in updated.error

    def test_tool_mastery_called_on_done(self, tmp_path, mock_tool_mastery):
        eng  = make_engine(tmp_path, tool_mastery=mock_tool_mastery)
        goal = eng.submit("Build something")
        eng.activate(goal.goal_id)
        plan = eng.store.get_goal(goal.goal_id).selected_plan
        task = plan.tasks[0]
        eng.mark_task_done(goal.goal_id, plan.plan_id, task.task_id)
        mock_tool_mastery.record_use.assert_called_once()

    def test_tool_mastery_called_on_failed(self, tmp_path, mock_tool_mastery):
        eng  = make_engine(tmp_path, tool_mastery=mock_tool_mastery)
        goal = eng.submit("Build something")
        eng.activate(goal.goal_id)
        plan = eng.store.get_goal(goal.goal_id).selected_plan
        task = plan.tasks[0]
        eng.mark_task_failed(goal.goal_id, plan.plan_id, task.task_id, error="boom")
        mock_tool_mastery.record_use.assert_called_once()

    def test_reflection_called_on_plan_complete(self, tmp_path, mock_memory,
                                                 mock_reflection, mock_learning):
        eng  = make_engine(tmp_path, memory=mock_memory,
                           reflection=mock_reflection, learning=mock_learning)
        goal = eng.submit("Research something")
        eng.activate(goal.goal_id)
        plan = eng.store.get_goal(goal.goal_id).selected_plan
        # Complete all tasks
        for task in plan.tasks:
            eng.mark_task_done(goal.goal_id, plan.plan_id, task.task_id, result="ok")
        mock_reflection.reflect.assert_called_once()
        mock_learning.learn_from.assert_called_once()

    def test_memory_episode_logged_on_plan_complete(self, tmp_path, mock_memory,
                                                     mock_reflection, mock_learning):
        eng  = make_engine(tmp_path, memory=mock_memory,
                           reflection=mock_reflection, learning=mock_learning)
        goal = eng.submit("Research something")
        eng.activate(goal.goal_id)
        plan = eng.store.get_goal(goal.goal_id).selected_plan
        for task in plan.tasks:
            eng.mark_task_done(goal.goal_id, plan.plan_id, task.task_id, result="ok")
        mock_memory.writer.store_episode.assert_called_once()

    def test_status_returns_plan_health(self, tmp_path):
        eng    = make_engine(tmp_path)
        goal   = eng.submit("Research something")
        eng.activate(goal.goal_id)
        health = eng.status(goal.goal_id)
        assert health is not None
        assert health.total_count >= 1

    def test_progress_report_non_empty(self, tmp_path):
        eng    = make_engine(tmp_path)
        goal   = eng.submit("Research something")
        eng.activate(goal.goal_id)
        report = eng.progress_report(goal.goal_id)
        assert "Research something" in report

    def test_replan_generates_new_plans(self, tmp_path):
        eng   = make_engine(tmp_path)
        goal  = eng.submit("Debug tokenizer failure")
        eng.activate(goal.goal_id)
        before_count = len(eng.store.get_goal(goal.goal_id).plans)
        eng.replan(goal.goal_id, reason="Too many failures")
        after_count = len(eng.store.get_goal(goal.goal_id).plans)
        assert after_count > before_count

    def test_works_without_optional_dependencies(self, tmp_path):
        eng  = PlannerEngine(store=PlannerStore(path=str(tmp_path / "g.jsonl")))
        goal = eng.submit("Research something")
        eng.activate(goal.goal_id)
        plan = eng.store.get_goal(goal.goal_id).selected_plan
        task = plan.tasks[0]
        # Should not raise even without memory/reflection/learning/tool_mastery
        eng.mark_task_done(goal.goal_id, plan.plan_id, task.task_id)

    def test_all_goals_and_active_goals(self, tmp_path):
        eng = make_engine(tmp_path)
        g1  = eng.submit("Goal 1")
        g2  = eng.submit("Goal 2")
        eng.activate(g1.goal_id)
        all_   = eng.all_goals()
        active = eng.active_goals()
        assert len(all_)   == 2
        assert len(active) == 1
