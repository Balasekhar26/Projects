"""Tests for Step 8.4 — Simulation Sandbox.

Tests cover:
1. Constitutional rules (Rules 1, 2, 3) — must never be violated
2. Scenario Path generation (A/B/C)
3. Resource Exhaustion Forecasting
4. Dependency Failure Propagation
5. Alignment Gate (constraint blocking, pass, warn)
6. Full project evaluation (end-to-end)
7. API endpoints (5 routes)
8. Regression: existing simulation and goal/PPM tests unaffected
"""
from __future__ import annotations

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_sandbox(tmp_path, monkeypatch):
    """Monkeypatches runtime_data_root and resets calibration cache."""
    import backend.core.action_memory as am_mod
    import backend.core.simulation_engine as se_mod
    import backend.core.simulation_calibration as sc_mod
    import backend.core.goal_memory as gm_mod
    import backend.core.project_memory as pm_mod

    monkeypatch.setattr(am_mod, "runtime_data_root", lambda: tmp_path)
    monkeypatch.setattr(se_mod, "runtime_data_root", lambda: tmp_path)
    monkeypatch.setattr(sc_mod, "runtime_data_root", lambda: tmp_path)
    monkeypatch.setattr(gm_mod, "load_config", lambda: _make_config(tmp_path))
    monkeypatch.setattr(pm_mod, "load_config", lambda: _make_config(tmp_path))
    sc_mod.SimulationCalibrator._cached_weights = {}
    gm_mod.GoalMemory._schema_ensured = False

    # Reset PPM schema flag
    import backend.core.personal_project_manager as ppm_mod
    import backend.core.project_memory as pm_mod2
    pm_mod2.ProjectMemory._schema_ensured = False

    yield tmp_path


def _make_config(tmp_path):
    """Minimal config object with sqlite_path pointing to tmp_path."""
    class _Cfg:
        sqlite_path = tmp_path / "kattappa.db"
    return _Cfg()


def _create_goal(title="Test Goal", priority="HIGH"):
    """Creates a goal via GoalMemory and returns goal_id."""
    from backend.core.goal_memory import GoalMemory
    goal = GoalMemory.create_goal(
        title=title,
        description="Goal for sandbox tests",
        priority=priority,
        success_criteria=["Done"],
        owner="test_owner",
    )
    return goal["goal_id"]


def _create_project_with_resources(goal_id: str, token_allocated: float, token_consumed: float):
    """Creates a PPM project with pre-allocated and consumed resources."""
    from backend.core.personal_project_manager import PersonalProjectManager
    proj = PersonalProjectManager.create_project(linked_goal_id=goal_id, title="Sandbox Test Project")
    p_id = proj["project_id"]
    PersonalProjectManager.allocate_resource(p_id, "TOKENS", token_allocated)
    if token_consumed > 0:
        # Consume directly via SQLite to bypass exhaustion guard for test setup
        from backend.core.project_memory import ProjectMemory
        conn = ProjectMemory._get_sqlite_conn()
        try:
            conn.execute(
                "UPDATE resources SET consumed_amount = ?, remaining_amount = ? WHERE project_id = ? AND resource_type = 'TOKENS'",
                (token_consumed, token_allocated - token_consumed, p_id)
            )
            conn.commit()
        finally:
            conn.close()
    return p_id


# ---------------------------------------------------------------------------
# Rule 1: Sandbox cannot authorize execution
# ---------------------------------------------------------------------------

class TestRule1NeverAuthorizes:
    def test_evaluate_plan_authorized_is_always_false(self, isolated_sandbox):
        from backend.core.simulation_sandbox import SimulationSandbox

        plan = [{"step_id": "s1", "agent": "coder", "action": "RUN_TESTS"}]
        report = SimulationSandbox.evaluate_plan(plan, goal="Build something")
        assert report.authorized is False, "authorized must always be False (Rule 1)"

    def test_evaluate_plan_to_dict_authorized_is_always_false(self, isolated_sandbox):
        from backend.core.simulation_sandbox import SimulationSandbox

        plan = [{"step_id": "s1", "agent": "coder", "action": "WRITE_FILE"}]
        d = SimulationSandbox.evaluate_plan(plan, goal="Write a file").to_dict()
        assert d["authorized"] is False

    def test_api_evaluate_always_returns_authorized_false(self, isolated_sandbox):
        resp = client.post("/sandbox/evaluate", json={"plan": [], "goal": "Nothing"})
        assert resp.status_code == 200
        assert resp.json()["authorized"] is False

    def test_api_constitution_describes_rule_1(self):
        resp = client.get("/sandbox/constitution")
        assert resp.status_code == 200
        data = resp.json()
        assert "SANDBOX_CANNOT_AUTHORIZE_EXECUTION" in data["constitution"]["rule_1"]


# ---------------------------------------------------------------------------
# Rule 2: Sandbox cannot create goals
# ---------------------------------------------------------------------------

class TestRule2CannotCreateGoals:
    def test_evaluate_plan_does_not_create_new_goal(self, isolated_sandbox):
        from backend.core.goal_memory import GoalMemory
        from backend.core.simulation_sandbox import SimulationSandbox

        goals_before = len(GoalMemory.list_goals())

        plan = [{"step_id": "s1", "agent": "browser", "action": "SEARCH_WEB"}]
        SimulationSandbox.evaluate_plan(plan, goal="Search for something")

        goals_after = len(GoalMemory.list_goals())
        assert goals_after == goals_before, (
            "Sandbox must not create goals (Rule 2). "
            f"Goal count changed from {goals_before} to {goals_after}."
        )

    def test_evaluate_project_plan_does_not_create_new_goal(self, isolated_sandbox):
        from backend.core.goal_memory import GoalMemory
        from backend.core.simulation_sandbox import SimulationSandbox

        goal_id = _create_goal("Rule2 Test Goal")
        p_id = _create_project_with_resources(goal_id, 100.0, 10.0)

        goals_before = len(GoalMemory.list_goals())

        plan = [{"step_id": "s1", "agent": "coder", "action": "WRITE_FILE"}]
        SimulationSandbox.evaluate_project_plan(p_id, plan, goal_id=goal_id)

        goals_after = len(GoalMemory.list_goals())
        assert goals_after == goals_before, "Sandbox must not create goals (Rule 2)."

    def test_sandbox_module_has_no_goal_write_imports(self):
        """Structural: verify simulation_sandbox imports no GoalMemory write methods at module level."""
        import inspect
        import backend.core.simulation_sandbox as sb_mod
        source = inspect.getsource(sb_mod)
        # Banned write-method calls at module level
        forbidden = ["GoalMemory.create_goal", "GoalMemory.update_goal",
                     "GoalMemory.archive_goal", "GoalMemory.delete_goal"]
        for f in forbidden:
            assert f not in source, f"Rule 2 violation: '{f}' found in simulation_sandbox.py"


# ---------------------------------------------------------------------------
# Rule 3: Sandbox cannot rewrite constraints
# ---------------------------------------------------------------------------

class TestRule3CannotRewriteConstraints:
    def test_absolute_policies_unchanged_after_sandbox_evaluation(self, isolated_sandbox):
        from backend.core.goal_memory import GoalMemory
        from backend.core.simulation_sandbox import SimulationSandbox

        policies_before = len(GoalMemory.ABSOLUTE_POLICIES)

        plan = [{"step_id": "s1", "agent": "coder", "action": "WRITE_FILE"}]
        SimulationSandbox.evaluate_plan(plan, goal="Change some policy")

        policies_after = len(GoalMemory.ABSOLUTE_POLICIES)
        assert policies_after == policies_before, (
            "Sandbox must not modify ABSOLUTE_POLICIES (Rule 3). "
            f"Policy count changed from {policies_before} to {policies_after}."
        )

    def test_constraint_violation_blocks_plan_but_does_not_modify_constraint(self, isolated_sandbox):
        from backend.core.goal_memory import GoalMemory
        from backend.core.simulation_sandbox import SimulationSandbox

        # Plan that references a forbidden core module name
        plan = [{"step_id": "s1", "agent": "coder", "action": "WRITE_FILE"}]
        report = SimulationSandbox.evaluate_plan(
            plan,
            plan_title="Modify backend/core/goal_memory.py",
            plan_description="Overwrite the goal memory module",
        )

        # Sandbox blocked it
        assert report.verdict.value == "BLOCKED"
        assert report.alignment_gate.constraint_violation is not None

        # But the constraint itself is unchanged
        assert len(GoalMemory.ABSOLUTE_POLICIES) >= 2  # policies still exist


# ---------------------------------------------------------------------------
# Scenario Path Generation
# ---------------------------------------------------------------------------

class TestScenarioPathGeneration:
    def test_three_paths_always_generated(self, isolated_sandbox):
        from backend.core.simulation_sandbox import SimulationSandbox

        plan = [{"step_id": "s1", "agent": "coder", "action": "RUN_TESTS"}]
        report = SimulationSandbox.evaluate_plan(plan, goal="Run tests")
        assert len(report.scenario_paths) == 3

    def test_path_ids_are_a_b_c(self, isolated_sandbox):
        from backend.core.simulation_sandbox import SimulationSandbox

        plan = [{"step_id": "s1", "agent": "coder", "action": "RUN_TESTS"}]
        paths = SimulationSandbox.evaluate_plan(plan, goal="Run tests").scenario_paths
        ids = {p.path_id for p in paths}
        assert ids == {"PATH_A", "PATH_B", "PATH_C"}

    def test_optimistic_better_than_pessimistic(self, isolated_sandbox):
        from backend.core.simulation_sandbox import SimulationSandbox

        plan = [{"step_id": "s1", "agent": "coder", "action": "RUN_TESTS"}]
        paths = {p.path_id: p for p in SimulationSandbox.evaluate_plan(plan, goal="Run tests").scenario_paths}
        assert paths["PATH_A"].success_probability >= paths["PATH_B"].success_probability
        assert paths["PATH_B"].success_probability >= paths["PATH_C"].success_probability
        assert paths["PATH_A"].risk_score <= paths["PATH_B"].risk_score
        assert paths["PATH_B"].risk_score <= paths["PATH_C"].risk_score


# ---------------------------------------------------------------------------
# Resource Exhaustion Forecasting
# ---------------------------------------------------------------------------

class TestResourceExhaustionForecasting:
    def test_high_burn_triggers_exhaustion_warning(self, isolated_sandbox):
        from backend.core.simulation_sandbox import ResourceExhaustionForecast

        goal_id = _create_goal("Exhaustion Test Goal")
        # 95% consumed out of 100 → should trigger warning after estimated additional 20%
        p_id = _create_project_with_resources(goal_id, 100.0, 75.0)
        forecast = ResourceExhaustionForecast.run(p_id)

        assert forecast.any_exhaustion_risk is True
        assert len(forecast.exhaustion_warning) > 0
        assert any(r.will_exhaust for r in forecast.resources)

    def test_low_burn_does_not_trigger_exhaustion(self, isolated_sandbox):
        from backend.core.simulation_sandbox import ResourceExhaustionForecast

        goal_id = _create_goal("Low Burn Goal")
        # 20% consumed → well within safe threshold
        p_id = _create_project_with_resources(goal_id, 100.0, 20.0)
        forecast = ResourceExhaustionForecast.run(p_id)

        assert forecast.any_exhaustion_risk is False
        assert not any(r.will_exhaust for r in forecast.resources)

    def test_exhaustion_triggers_recommend_revise_verdict(self, isolated_sandbox):
        from backend.core.simulation_sandbox import SimulationSandbox

        goal_id = _create_goal("High Burn Project Goal")
        p_id = _create_project_with_resources(goal_id, 100.0, 75.0)

        plan = [{"step_id": "s1", "agent": "coder", "action": "RUN_TESTS"}]
        report = SimulationSandbox.evaluate_project_plan(p_id, plan, goal_id=goal_id)

        # Resource exhaustion → must be RECOMMEND_REVISE or BLOCKED (never PROCEED)
        assert report.verdict.value in {"RECOMMEND_REVISE", "BLOCKED"}

    def test_api_resource_forecast_endpoint(self, isolated_sandbox):
        goal_id = _create_goal("API Forecast Goal")
        p_id = _create_project_with_resources(goal_id, 100.0, 50.0)

        resp = client.post(f"/sandbox/resource-forecast/{p_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "resources" in data


# ---------------------------------------------------------------------------
# Dependency Failure Propagation
# ---------------------------------------------------------------------------

class TestDependencyFailurePropagation:
    def _create_two_linked_projects(self):
        """Creates two projects where proj_b depends on proj_a (HARD)."""
        from backend.core.personal_project_manager import PersonalProjectManager

        goal_a = _create_goal("Dependency Goal A")
        goal_b = _create_goal("Dependency Goal B")
        proj_a = PersonalProjectManager.create_project(linked_goal_id=goal_a, title="Project A")
        proj_b = PersonalProjectManager.create_project(linked_goal_id=goal_b, title="Project B")
        PersonalProjectManager.add_project_dependency(
            project_id=proj_b["project_id"],
            depends_on_project_id=proj_a["project_id"],
            dependency_type="HARD",
        )
        return proj_a["project_id"], proj_b["project_id"]

    def test_hard_dependency_slip_propagates_delay(self, isolated_sandbox):
        from backend.core.simulation_sandbox import DependencyFailureModel

        p_a, p_b = self._create_two_linked_projects()
        report = DependencyFailureModel.propagate(p_b)

        assert len(report.scenarios) > 0
        slip_scenarios = [s for s in report.scenarios if s.failure_mode == "SLIP"]
        assert len(slip_scenarios) > 0
        # HARD dependency: 1-day slip multiplier = 1.0, so 7-day slip = 7-day delay
        seven_day = next((s for s in slip_scenarios if s.slip_days == 7.0), None)
        assert seven_day is not None
        assert seven_day.cascaded_delay_days == pytest.approx(7.0, abs=0.01)

    def test_hard_dependency_failure_marks_blocking_possible(self, isolated_sandbox):
        from backend.core.simulation_sandbox import DependencyFailureModel

        p_a, p_b = self._create_two_linked_projects()
        report = DependencyFailureModel.propagate(p_b)

        assert report.blocking_failure_possible is True

    def test_no_dependencies_returns_clean_report(self, isolated_sandbox):
        from backend.core.simulation_sandbox import DependencyFailureModel

        goal_id = _create_goal("No Deps Goal")
        p_id = _create_project_with_resources(goal_id, 50.0, 0.0)
        report = DependencyFailureModel.propagate(p_id)

        assert len(report.scenarios) == 0
        assert report.blocking_failure_possible is False
        assert report.worst_case_delay_days == 0.0

    def test_api_dependency_propagation_endpoint(self, isolated_sandbox):
        goal_id = _create_goal("API Dep Goal")
        p_id = _create_project_with_resources(goal_id, 50.0, 5.0)

        resp = client.post(f"/sandbox/dependency-propagation/{p_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "scenarios" in data


# ---------------------------------------------------------------------------
# Alignment Gate
# ---------------------------------------------------------------------------

class TestAlignmentGate:
    def test_constraint_violation_blocked(self, isolated_sandbox):
        from backend.core.simulation_sandbox import AlignmentGate, AlignmentVerdict

        result = AlignmentGate.check(
            plan_steps=[],
            plan_title="Modify backend/core/goal_memory.py",
            plan_description="Overwrite the goal memory module",
        )
        assert result.verdict == AlignmentVerdict.BLOCKED
        assert result.constraint_violation is not None

    def test_clean_plan_passes(self, isolated_sandbox):
        from backend.core.simulation_sandbox import AlignmentGate, AlignmentVerdict

        result = AlignmentGate.check(
            plan_steps=[{"step_id": "s1", "agent": "coder", "action": "RUN_TESTS"}],
            plan_title="Run the test suite",
            plan_description="Execute all backend tests",
        )
        assert result.verdict in {AlignmentVerdict.PASS, AlignmentVerdict.WARN}

    def test_archived_goal_blocks_alignment(self, isolated_sandbox):
        from backend.core.goal_memory import GoalMemory
        from backend.core.simulation_sandbox import AlignmentGate, AlignmentVerdict

        goal_id = _create_goal("Archived Goal")
        GoalMemory.update_goal_status(goal_id, "ARCHIVED", reason="Test archival")

        result = AlignmentGate.check(
            plan_steps=[{"step_id": "s1", "agent": "coder", "action": "RUN_TESTS"}],
            goal_id=goal_id,
        )
        assert result.verdict == AlignmentVerdict.BLOCKED

    def test_active_goal_passes_alignment(self, isolated_sandbox):
        from backend.core.simulation_sandbox import AlignmentGate, AlignmentVerdict

        goal_id = _create_goal("Active Goal")
        result = AlignmentGate.check(
            plan_steps=[{"step_id": "s1", "agent": "coder", "action": "RUN_TESTS"}],
            goal_id=goal_id,
        )
        assert result.verdict in {AlignmentVerdict.PASS, AlignmentVerdict.WARN}
        assert result.constraint_violation is None


# ---------------------------------------------------------------------------
# Full Project Sandbox Evaluation (End-to-End)
# ---------------------------------------------------------------------------

class TestFullProjectSandboxEvaluation:
    def test_full_evaluation_returns_complete_report(self, isolated_sandbox):
        from backend.core.simulation_sandbox import SimulationSandbox

        goal_id = _create_goal("Full Eval Goal")
        p_id = _create_project_with_resources(goal_id, 200.0, 30.0)

        plan = [
            {"step_id": "s1", "agent": "coder", "action": "WRITE_FILE"},
            {"step_id": "s2", "agent": "coder", "action": "RUN_TESTS"},
        ]
        report = SimulationSandbox.evaluate_project_plan(p_id, plan, goal_id=goal_id)

        d = report.to_dict()
        assert d["sandbox_version"] == "8.4"
        assert d["authorized"] is False
        assert d["constitution_enforced"] is True
        assert "constitution" in d
        assert len(d["scenario_paths"]) == 3
        assert d["resource_forecast"] is not None
        assert d["dependency_propagation"] is not None
        assert d["alignment_gate"] is not None
        assert "verdict" in d

    def test_api_full_project_evaluate_returns_200(self, isolated_sandbox):
        goal_id = _create_goal("API Full Eval Goal")
        p_id = _create_project_with_resources(goal_id, 200.0, 20.0)

        resp = client.post(
            f"/sandbox/evaluate/project/{p_id}",
            json={
                "plan": [{"step_id": "s1", "agent": "coder", "action": "RUN_TESTS"}],
                "goal": "Test everything",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["authorized"] is False
        assert data["sandbox_version"] == "8.4"
        assert len(data["scenario_paths"]) == 3


# ---------------------------------------------------------------------------
# API: Constitution Endpoint
# ---------------------------------------------------------------------------

class TestConstitutionEndpoint:
    def test_constitution_contains_all_four_rules(self):
        resp = client.get("/sandbox/constitution")
        assert resp.status_code == 200
        c = resp.json()["constitution"]
        assert "SANDBOX_CANNOT_AUTHORIZE_EXECUTION" in c["rule_1"]
        assert "SANDBOX_CANNOT_CREATE_GOALS" in c["rule_2"]
        assert "SANDBOX_CANNOT_REWRITE_CONSTRAINTS" in c["rule_3"]
        assert "REASON_BEFORE_ACTION" in c["rule_4"]

    def test_constitution_is_read_only_get(self):
        """Constitution endpoint must be GET (never POST/PUT)."""
        resp = client.post("/sandbox/constitution", json={})
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Regression: Existing simulation tests must still pass
# ---------------------------------------------------------------------------

class TestRegressionExistingSimulation:
    def test_simulate_plan_still_works(self, isolated_sandbox):
        """Core SimulationEngine.simulate_plan() is unchanged."""
        from backend.core.simulation_engine import SimulationEngine

        report = SimulationEngine.simulate_plan(
            [{"step_id": "s1", "agent": "coder", "action": "RUN_TESTS"}],
            goal="Run tests regression",
            workflow_id="wf_regression",
        )
        d = report.to_dict()
        assert 0.0 < d["success_probability"] <= 1.0
        assert d["step_predictions"][0]["action"] == "RUN_TESTS"

    def test_simulate_api_still_works(self, isolated_sandbox):
        """/simulate/plan API endpoint is unchanged."""
        resp = client.post(
            "/simulate/plan",
            json={
                "goal": "Regression test",
                "workflow_id": "wf_reg",
                "plan": [{"step_id": "s1", "agent": "coder", "action": "RUN_TESTS"}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["goal"] == "Regression test"
        assert data["step_predictions"][0]["action"] == "RUN_TESTS"
