"""
Tests for Step 28 — Autonomous Workflow Engine
================================================

All tests are hermetic (no network, no disk I/O beyond tmp_path).

Covers:

Schema
  - WorkflowEvent.to_log_line() contains timestamp and icon
  - WorkflowResult.execution_log() includes goal title and events
  - WorkflowResult.to_dict() roundtrip

ToolRouter
  - execute() routes to correct handler by tool_hint
  - execute() returns (True, str) for all default hints
  - execute() returns (False, str) when handler raises
  - register() overrides default handler
  - dry_run=True stubs HIGH-risk tools
  - dry_run=False executes HIGH-risk tools normally (stub impl)
  - research_engine handler called when research_engine connected
  - memory_writer handler stores to memory
  - web_search alias routes to research handler
  - default handler returns True for unknown hints
  - known_tools() returns non-empty list

WorkflowEngine
  - run() returns WorkflowResult
  - status COMPLETED when all tasks succeed
  - tasks_done count matches plan task count
  - events log contains GOAL_SUBMITTED, PLAN_ACTIVATED, TASK_COMPLETED, WORKFLOW_DONE
  - TASK_FAILED logged when router returns failure
  - dry_run=True prevents HIGH-risk tool execution
  - max_steps safety halt fires correctly
  - max_replans limit triggers FAILED status
  - on_task_start hook is called
  - on_task_done hook is called
  - run() works without optional engines (no-op handlers)
  - replan triggered when plan has >40% failure rate
  - WorkflowEngine integrates with real PlannerEngine + PlannerStore
  - multiple sequential goals produce independent results
  - run_goal_id() returns None for unknown goal
  - tasks_failed count matches failed task count

Integration
  - Full autonomous loop: submit → execute all → reflect triggered
  - ReflectionEngine.reflect() called when plan completes via engine
"""

import pytest
from unittest.mock import MagicMock, call, patch
from kattappa_runtime.planner.engine     import PlannerEngine
from kattappa_runtime.planner.store      import PlannerStore
from kattappa_runtime.planner.schema     import Task, RiskLevel, TaskStatus, PlanStatus
from kattappa_runtime.workflow.schema    import (
    WorkflowResult, WorkflowEvent, WorkflowStatus, EventType
)
from kattappa_runtime.workflow.router    import ToolRouter
from kattappa_runtime.workflow.engine    import WorkflowEngine


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def tmp_planner(tmp_path):
    store = PlannerStore(path=str(tmp_path / "goals.jsonl"))
    return PlannerEngine(store=store)


@pytest.fixture
def mock_reflection():
    from kattappa_runtime.reflection.schema import Reflection, OutcomeLabel
    eng = MagicMock()
    eng.reflect.return_value = Reflection(
        domain="test", outcome=OutcomeLabel.SUCCESS,
        lesson="workflow completed", confidence_delta=0.05,
    )
    return eng


@pytest.fixture
def mock_learning():
    return MagicMock()


@pytest.fixture
def mock_memory():
    m = MagicMock()
    m.writer = MagicMock()
    m.writer.store_episode = MagicMock()
    m.writer.store_fact    = MagicMock()
    return m


@pytest.fixture
def mock_research():
    from kattappa_runtime.research.schema import ResearchReport
    eng = MagicMock()
    eng.research.return_value = ResearchReport(
        topic="impedance matching",
        summary="Smith charts explain impedance matching.",
        key_facts=["Impedance = Z = R + jX"],
        findings=[],
    )
    return eng


def make_engine(tmp_path, planner=None, router=None, **kwargs):
    if planner is None:
        store  = PlannerStore(path=str(tmp_path / "goals.jsonl"))
        planner = PlannerEngine(store=store)
    router = router or ToolRouter()
    return WorkflowEngine(planner_engine=planner, tool_router=router, **kwargs)


# ===========================================================================
# Schema Tests
# ===========================================================================

class TestWorkflowSchema:
    def test_event_log_line_has_timestamp(self):
        ev = WorkflowEvent(event_type=EventType.TASK_STARTED,
                           message="Starting task", task_title="Do X")
        line = ev.to_log_line()
        assert ":" in line  # HH:MM:SS

    def test_event_log_line_has_message(self):
        ev = WorkflowEvent(event_type=EventType.TASK_COMPLETED,
                           message="Task done", result="OK")
        assert "Task done" in ev.to_log_line()
        assert "OK" in ev.to_log_line()

    def test_execution_log_includes_goal_title(self):
        result = WorkflowResult(goal_title="Research impedance matching")
        result.events.append(WorkflowEvent(event_type=EventType.GOAL_SUBMITTED,
                                           message="Submitted"))
        log = result.execution_log()
        assert "Research impedance matching" in log

    def test_execution_log_includes_all_events(self):
        result = WorkflowResult(goal_title="T")
        for et in [EventType.GOAL_SUBMITTED, EventType.PLAN_ACTIVATED,
                   EventType.TASK_COMPLETED, EventType.WORKFLOW_DONE]:
            result.events.append(WorkflowEvent(event_type=et, message=et.value))
        log = result.execution_log()
        assert "goal_submitted"  in log
        assert "workflow_done"   in log

    def test_to_dict_roundtrip(self):
        result = WorkflowResult(
            goal_title="T", domain="rf", status=WorkflowStatus.COMPLETED,
            tasks_total=3, tasks_done=3,
        )
        d = result.to_dict()
        assert d["status"]      == "completed"
        assert d["tasks_total"] == 3
        assert d["goal_title"]  == "T"


# ===========================================================================
# ToolRouter Tests
# ===========================================================================

class TestToolRouter:
    def test_default_handler_returns_success(self):
        router = ToolRouter()
        task   = Task(title="Do X", tool_hint="unknown_tool")
        ok, _  = router.execute(task)
        assert ok is True

    def test_all_default_hints_return_success(self):
        router = ToolRouter()
        for hint in ["research_engine", "memory_writer", "skill_memory",
                     "reflection_engine", "code_runner", "planner",
                     "synthesizer", "git", "web_search", "wikipedia"]:
            task = Task(title="t", tool_hint=hint)
            ok, result = router.execute(task)
            assert ok is True, f"Handler for '{hint}' failed: {result}"

    def test_register_overrides_handler(self):
        router = ToolRouter()
        router.register("my_custom_tool", lambda t: (True, "custom!"))
        task  = Task(title="t", tool_hint="my_custom_tool")
        ok, r = router.execute(task)
        assert ok is True
        assert r  == "custom!"

    def test_dry_run_stubs_high_risk(self):
        router  = ToolRouter()
        task    = Task(title="Run code", tool_hint="code_runner",
                       risk_level=RiskLevel.HIGH)
        ok, res = router.execute(task, dry_run=True)
        assert ok is True
        assert "DRY_RUN" in res

    def test_dry_run_false_executes_code_runner(self):
        router  = ToolRouter()
        task    = Task(title="Run code", tool_hint="code_runner")
        ok, res = router.execute(task, dry_run=False)
        assert ok is True
        # Should be the stub result (not DRY_RUN)
        assert "STUB" in res

    def test_research_engine_handler_called(self, mock_research):
        router = ToolRouter(research_engine=mock_research)
        task   = Task(title="Research RF", tool_hint="research_engine",
                      description="Impedance matching overview")
        ok, _  = router.execute(task)
        assert ok is True
        mock_research.research.assert_called_once()

    def test_memory_writer_handler_called(self, mock_memory):
        router = ToolRouter(memory=mock_memory)
        task   = Task(title="Store fact", tool_hint="memory_writer")
        ok, _  = router.execute(task)
        assert ok is True
        mock_memory.writer.store_fact.assert_called_once()

    def test_handler_failure_returns_false(self):
        router = ToolRouter()
        def bad_handler(t): raise RuntimeError("boom")
        router.register("bad_tool", bad_handler)
        task   = Task(title="t", tool_hint="bad_tool")
        ok, r  = router.execute(task)
        assert ok is False
        assert "boom" in r

    def test_web_search_alias_routes_to_research(self, mock_research):
        router = ToolRouter(research_engine=mock_research)
        task   = Task(title="Search RF", tool_hint="web_search",
                      description="RF amplifiers")
        router.execute(task)
        mock_research.research.assert_called_once()

    def test_known_tools_non_empty(self):
        router = ToolRouter()
        tools  = router.known_tools()
        assert len(tools) > 5
        assert "research_engine" in tools
        assert "code_runner"     in tools


# ===========================================================================
# WorkflowEngine Tests
# ===========================================================================

class TestWorkflowEngine:
    def test_run_returns_workflow_result(self, tmp_path):
        eng    = make_engine(tmp_path)
        result = eng.run("Research neural nets")
        assert isinstance(result, WorkflowResult)

    def test_status_completed_on_success(self, tmp_path):
        eng    = make_engine(tmp_path)
        result = eng.run("Research neural nets")
        assert result.status == WorkflowStatus.COMPLETED

    def test_tasks_done_matches_plan(self, tmp_path):
        eng    = make_engine(tmp_path)
        result = eng.run("Research neural nets")
        assert result.tasks_done > 0
        assert result.tasks_done == result.tasks_total

    def test_events_contain_key_milestones(self, tmp_path):
        eng    = make_engine(tmp_path)
        result = eng.run("Research neural nets")
        event_types = {e.event_type for e in result.events}
        assert EventType.GOAL_SUBMITTED  in event_types
        assert EventType.PLAN_ACTIVATED  in event_types
        assert EventType.TASK_COMPLETED  in event_types
        assert EventType.WORKFLOW_DONE   in event_types

    def test_task_failed_logged_on_router_failure(self, tmp_path):
        def always_fail(t): return (False, "intentional failure")
        router = ToolRouter()
        # Override all defaults to fail
        for hint in router.known_tools():
            router.register(hint, always_fail)
        router.register("default", always_fail)
        eng    = make_engine(tmp_path, router=router,
                             max_replans=0, max_steps=5)
        result = eng.run("Research something")
        event_types = {e.event_type for e in result.events}
        assert EventType.TASK_FAILED in event_types

    def test_max_steps_triggers_safety_halt(self, tmp_path):
        """max_steps=0 means the engine halts before executing any task."""
        eng    = make_engine(tmp_path, max_steps=0)
        result = eng.run("Build something huge")
        assert result.status == WorkflowStatus.STOPPED
        event_types = {e.event_type for e in result.events}
        assert EventType.SAFETY_HALT in event_types

    def test_dry_run_stubs_code_runner(self, tmp_path):
        """In dry_run mode, code_runner tasks should show DRY_RUN result."""
        dry_results = []

        def capture_done(task, result):
            if "code_runner" in task.tool_hint:
                dry_results.append(result)

        eng = make_engine(tmp_path, dry_run=True, on_task_done=capture_done)
        eng.run("Build a calculator")
        # At least one code_runner task should have been stubbed
        assert any("DRY_RUN" in r for r in dry_results)

    def test_on_task_start_hook_called(self, tmp_path):
        started = []
        eng     = make_engine(tmp_path, on_task_start=lambda t: started.append(t.title))
        eng.run("Research neural nets")
        assert len(started) > 0

    def test_on_task_done_hook_called(self, tmp_path):
        done = []
        eng  = make_engine(tmp_path, on_task_done=lambda t, r: done.append(t.title))
        eng.run("Research neural nets")
        assert len(done) > 0

    def test_works_without_optional_engines(self, tmp_path):
        """Router with no optional engines still completes successfully."""
        router = ToolRouter()
        eng    = make_engine(tmp_path, router=router)
        result = eng.run("Research something")
        assert result.status == WorkflowStatus.COMPLETED

    def test_multiple_sequential_goals_independent(self, tmp_path):
        eng = make_engine(tmp_path)
        r1  = eng.run("Research RF systems", domain="rf")
        r2  = eng.run("Research neural nets", domain="ml")
        assert r1.goal_id != r2.goal_id
        assert r1.status  == WorkflowStatus.COMPLETED
        assert r2.status  == WorkflowStatus.COMPLETED

    def test_run_goal_id_unknown_returns_none(self, tmp_path):
        eng    = make_engine(tmp_path)
        result = eng.run_goal_id("nonexistent-goal-id")
        assert result is None

    def test_tasks_failed_count_accurate(self, tmp_path):
        fail_count = 0

        def count_fails(t): return (False, "fail")

        router = ToolRouter()
        # Make first 2 tools fail, rest succeed
        calls = [0]
        def sometimes_fail(t):
            calls[0] += 1
            if calls[0] <= 1:
                return (False, "forced fail")
            return (True, "ok")

        for hint in router.known_tools():
            router.register(hint, sometimes_fail)
        router.register("default", sometimes_fail)

        eng    = make_engine(tmp_path, router=router, max_replans=0)
        result = eng.run("Research something")
        # tasks_failed should be consistent with events
        fail_events = [e for e in result.events if e.event_type == EventType.TASK_FAILED]
        assert result.tasks_failed == len(fail_events)

    def test_replan_generates_fresh_tasks(self, tmp_path):
        """When failure rate exceeds threshold, replan triggers and creates new plan."""
        fail_count = [0]

        def controlled_fail(t):
            fail_count[0] += 1
            # Fail first 3 tasks to trigger replan (>40% of 3-task fast plan)
            if fail_count[0] <= 3:
                return (False, "forced fail")
            return (True, "ok")

        router = ToolRouter()
        for hint in router.known_tools():
            router.register(hint, controlled_fail)
        router.register("default", controlled_fail)

        eng    = make_engine(tmp_path, router=router,
                             max_replans=1, max_steps=25)
        result = eng.run("Research RF")
        replan_events = [e for e in result.events
                         if e.event_type == EventType.REPLAN_TRIGGERED]
        assert len(replan_events) >= 1


# ===========================================================================
# Integration Tests
# ===========================================================================

class TestWorkflowIntegration:
    def test_full_loop_with_research_engine(self, tmp_path, mock_research):
        """Research tasks actually call the research engine."""
        router = ToolRouter(research_engine=mock_research)
        eng    = make_engine(tmp_path, router=router)
        result = eng.run("Research impedance matching", domain="rf_systems")
        assert result.status == WorkflowStatus.COMPLETED
        # Research engine should have been called for research_engine tasks
        assert mock_research.research.call_count >= 1

    def test_reflection_triggered_via_planner_on_complete(
        self, tmp_path, mock_reflection, mock_learning, mock_memory
    ):
        """PlannerEngine fires reflection when plan completes through WorkflowEngine."""
        store   = PlannerStore(path=str(tmp_path / "goals.jsonl"))
        planner = PlannerEngine(
            store=store,
            reflection_engine=mock_reflection,
            learning_engine=mock_learning,
            memory=mock_memory,
        )
        router = ToolRouter()
        eng    = WorkflowEngine(planner_engine=planner, tool_router=router)
        result = eng.run("Research neural nets", domain="ml")

        assert result.status == WorkflowStatus.COMPLETED
        mock_reflection.reflect.assert_called_once()
        mock_learning.learn_from.assert_called_once()
        mock_memory.writer.store_episode.assert_called_once()

    def test_execution_log_is_human_readable(self, tmp_path):
        eng    = make_engine(tmp_path)
        result = eng.run("Debug tokenizer failure", domain="ml")
        log    = result.execution_log()
        # Should contain the goal name and task names
        assert "Debug tokenizer failure" in log
        assert len(log.split("\n")) > 5   # multi-line, not empty

    def test_workflow_result_summary_set(self, tmp_path):
        eng    = make_engine(tmp_path)
        result = eng.run("Research something")
        assert result.summary != ""
        assert result.completed_at != ""
