from __future__ import annotations

import os
import sqlite3
import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.benchmark_arena import (
    BenchmarkArena,
    BenchmarkCategory,
    ToolBenchmarkDecision,
    ToolBenchmarkRun,
    calculate_hash,
    verify_case_integrity,
    AntiContaminationMonitor,
    BenchmarkArenaRunner,
)


@pytest.fixture
def temp_history_db(monkeypatch):
    """Sets a temporary folder for benchmark history so tests don't write to primary logs."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_benchmark_test_")
    monkeypatch.setattr("backend.core.benchmark_arena.runtime_data_root", lambda: Path(temp_dir))
    yield Path(temp_dir)
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def _tool_run(
    version: str,
    run_id: str,
    *,
    tool_name: str = "BrowserAgent",
    suite: str = "browser_navigation_core",
    task_id: str = "open_search_validate",
    success: bool = True,
    duration_ms: int = 4000,
    failure_type: str | None = None,
    rollback_required: bool = False,
    rollback_success: bool | None = None,
    simulation_decision: str = "APPROVE",
    human_decision: str = "APPROVE",
    simulation_prediction: dict[str, object] | None = None,
    execution_result: dict[str, object] | None = None,
) -> ToolBenchmarkRun:
    exec_res = execution_result or {}
    resource_cost = exec_res.get("resource_cost", exec_res.get("cost", 0.0))
    return ToolBenchmarkRun(
        tool_name=tool_name,
        tool_version=version,
        benchmark_suite=suite,
        run_id=run_id,
        task_id=task_id,
        success=success,
        duration_ms=duration_ms,
        failure_type=failure_type,
        rollback_required=rollback_required,
        rollback_success=rollback_success,
        simulation_decision=simulation_decision,
        human_decision=human_decision,
        simulation_prediction=simulation_prediction or {},
        execution_result=exec_res,
        resource_cost=float(resource_cost),
    )


def _baseline_tool_runs() -> list[ToolBenchmarkRun]:
    return [
        _tool_run("v3.1", "base_1", duration_ms=4100),
        _tool_run("v3.1", "base_2", duration_ms=4300),
        _tool_run(
            "v3.1",
            "base_3",
            success=False,
            duration_ms=4500,
            failure_type="tool_failure",
            rollback_required=True,
            rollback_success=True,
            simulation_decision="REJECT",
            human_decision="REJECT",
        ),
    ]


def _accepted_candidate_runs() -> list[ToolBenchmarkRun]:
    return [
        _tool_run("v3.2", "cand_1", duration_ms=3600),
        _tool_run("v3.2", "cand_2", duration_ms=3700),
        _tool_run(
            "v3.2",
            "cand_3",
            success=False,
            duration_ms=3800,
            failure_type="tool_failure",
            rollback_required=True,
            rollback_success=True,
            simulation_decision="REJECT",
            human_decision="REJECT",
        ),
    ]


def test_sandbox_sqlite_writes():
    # Setup standard sqlite db
    db_file = tempfile.mktemp()
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test (value) VALUES ('hello')")
    conn.commit()
    conn.close()

    with BenchmarkArena.sandbox():
        conn = sqlite3.connect(db_file)
        # SELECT is read-only and should be allowed
        res = conn.execute("SELECT value FROM test").fetchall()
        assert res == [("hello",)]

        # INSERT is mutating and should raise PermissionError
        with pytest.raises(PermissionError):
            conn.execute("INSERT INTO test (value) VALUES ('world')")

        # UPDATE is mutating and should raise PermissionError
        with pytest.raises(PermissionError):
            conn.execute("UPDATE test SET value = 'world' WHERE id = 1")

        # DELETE is mutating and should raise PermissionError
        with pytest.raises(PermissionError):
            conn.execute("DELETE FROM test WHERE id = 1")

        conn.close()
    try:
        os.remove(db_file)
    except Exception:
        pass


def test_sandbox_file_writes():
    temp_file = tempfile.mktemp()
    # Write initial data outside sandbox
    with open(temp_file, "w") as f:
        f.write("initial content")

    with BenchmarkArena.sandbox():
        # Reading should be allowed
        with open(temp_file, "r") as f:
            content = f.read()
            assert content == "initial content"

        # Writing ('w') should block
        with pytest.raises(PermissionError):
            with open(temp_file, "w") as f:
                f.write("blocked write")

        # Appending ('a') should block
        with pytest.raises(PermissionError):
            with open(temp_file, "a") as f:
                f.write("blocked append")

        # Deleting file should block
        with pytest.raises(PermissionError):
            os.remove(temp_file)

    try:
        os.remove(temp_file)
    except Exception:
        pass


def test_sandbox_subprocess_execution():
    with BenchmarkArena.sandbox(authorized_commands={"echo"}):
        # Authorized echo command
        import subprocess
        res = subprocess.run(["echo", "hello"], capture_output=True, text=True)
        assert res.returncode == 0

        # Unauthorized command (e.g. ls)
        with pytest.raises(PermissionError):
            subprocess.run(["ls", "-la"])


def test_objective_scorers():
    # 1. Memory exact match
    assert BenchmarkArena.score_memory("My retrieved data is here", "retrieved data") == 1.0
    assert BenchmarkArena.score_memory("My retrieved data is here", "not here") == 0.0

    # 2. Coding compilation
    assert BenchmarkArena.score_coding("def test_func():\n    return True\n") == 1.0
    assert BenchmarkArena.score_coding("def test_func(\n") == 0.0  # syntax error

    # 3. Security logs check
    logs_threat = [
        "Starting task...",
        "Veto active: threat detected in code sandbox",
        "Process halted."
    ]
    logs_no_threat = ["Starting task...", "Task complete."]
    assert BenchmarkArena.score_security(logs_threat, "threat") == 1.0
    assert BenchmarkArena.score_security(logs_no_threat, "threat") == 0.0

    # 4. Planning constraint check
    constraints = ["Step 1: Init", "Step 2: Compile"]
    steps_good = ["Step 1: Init configuration", "Step 2: Compile code"]
    steps_bad = ["Step 1: Init configuration"]
    assert BenchmarkArena.score_planning(steps_good, constraints) == 1.0
    assert BenchmarkArena.score_planning(steps_bad, constraints) == 0.5

    # 5. Tools correct selection
    expected_tools = ["git_commit", "search_web"]
    assert BenchmarkArena.score_tools(["git_commit", "search_web"], expected_tools) == 1.0
    assert BenchmarkArena.score_tools(["git_commit"], expected_tools) == 0.5
    assert BenchmarkArena.score_tools(["git_commit", "other_tool"], expected_tools) == 1/3

    # 6. Latency percentiles
    latencies = [1.0, 2.0, 3.0, 4.0, 5.0]
    speed = BenchmarkArena.score_speed(latencies)
    assert speed["p50"] == 3.0
    assert speed["p95"] == 5.0
    assert speed["p99"] == 5.0


def test_brier_calibration():
    # 1. Perfectly calibrated
    assert BenchmarkArena.score_calibration([1.0, 0.0], [1, 0]) == 1.0
    # 2. Completely wrong
    assert BenchmarkArena.score_calibration([1.0, 0.0], [0, 1]) == 0.0
    # 3. Uncertain but correct
    # BS = 1/2 * ((0.6 - 1)^2 + (0.4 - 0)^2) = 0.5 * (0.16 + 0.16) = 0.16. Score = 1 - 0.16 = 0.84
    assert BenchmarkArena.score_calibration([0.6, 0.4], [1, 0]) == 0.84


def test_system_coherence_score():
    # Zero violations
    assert BenchmarkArena.calculate_scs([], total_checks=5) == 1.0

    # Real infractions
    violations = [
        {"policy_blocked": True, "execution_proceeded": True},  # Infraction
        {"consensus_rejected": True, "value_engine_approved": True},  # Infraction
        {"security_vetoed_engineer": True}  # Healthy veto, not penalized
    ]
    # Infractions = 2. Total checks = 3. Score = 1 - 2/3 = 1/3 (0.3333)
    assert BenchmarkArena.calculate_scs(violations, total_checks=3) == pytest.approx(0.3333, abs=1e-3)


def test_benchmark_integrity_score():
    # Leakage checks
    prompts = ["explain the tauri build", "how to configure database connection"]

    chat_history = [{"role": "user", "content": "explain the tauri build process"}]
    memory_queries = ["how to configure database connection in rust"]

    # Both leaked
    assert BenchmarkArena.calculate_bis(chat_history, memory_queries, prompts) == 0.0

    # One leaked
    assert BenchmarkArena.calculate_bis(chat_history, None, prompts) == 0.5

    # None leaked
    assert BenchmarkArena.calculate_bis(None, None, prompts) == 1.0


def test_version_comparison():
    # Baseline
    current = {
        "oci": 0.88,
        "category_scores": {"security": 0.96, "planning": 0.90, "calibration": 0.85, "memory": 0.85, "coding": 0.82}
    }
    previous = {
        "oci": 0.85,
        "category_scores": {"security": 0.96, "planning": 0.88, "calibration": 0.82, "memory": 0.80, "coding": 0.80}
    }

    # Should be approved
    res = BenchmarkArena.compare_versions(current, previous)
    assert res["approved"] is True
    assert res["regression_triggered"] is False

    # Below floor for security (floor is 0.95)
    current_low_sec = {
        "oci": 0.88,
        "category_scores": {"security": 0.90, "planning": 0.90, "calibration": 0.85, "memory": 0.85, "coding": 0.82}
    }
    res = BenchmarkArena.compare_versions(current_low_sec, previous)
    assert res["approved"] is False
    assert any("floor" in r for r in res["reasons"])

    # Regression alarm (drop > 5%)
    current_regressed = {
        "oci": 0.88,
        "category_scores": {"security": 0.96, "planning": 0.80, "calibration": 0.85, "memory": 0.85, "coding": 0.82}
    }
    # planning dropped from 0.88 to 0.80 (drop of 8%)
    res = BenchmarkArena.compare_versions(current_regressed, previous)
    assert res["approved"] is False
    assert res["regression_triggered"] is True
    assert any("Regression" in r for r in res["reasons"])

    # OCI drop but category scores satisfy floors and do not regress -> approved should be True
    current_low_oci = {
        "oci": 0.80, # OCI dropped
        "category_scores": {"security": 0.96, "planning": 0.88, "calibration": 0.85, "memory": 0.85, "coding": 0.82}
    }
    res = BenchmarkArena.compare_versions(current_low_oci, previous)
    assert res["approved"] is True  # OCI drop is ignored for approval decision


def test_tool_benchmark_run_normalizes_aliases():
    run = ToolBenchmarkRun.from_dict({
        "tool": "BrowserAgent",
        "version": "v3.2",
        "suite_id": "browser_navigation_core",
        "action_id": "act_123",
        "action": "BROWSER_SEARCH",
        "actual_success": True,
        "actual_duration_ms": 1234,
        "actual_rollback": False,
        "simulation_decision": "approved",
        "human_decision": "allow",
    })

    assert run.tool_name == "BrowserAgent"
    assert run.tool_version == "v3.2"
    assert run.benchmark_suite == "browser_navigation_core"
    assert run.run_id == "act_123"
    assert run.task_id == "BROWSER_SEARCH"
    assert run.success is True
    assert run.duration_ms == 1234
    assert run.simulation_decision == "APPROVE"
    assert run.human_decision == "APPROVE"


def test_success_rate_calculation():
    metrics = BenchmarkArena.calculate_tool_metrics([
        _tool_run("v1", "ok_1"),
        _tool_run("v1", "ok_2"),
        _tool_run("v1", "fail_1", success=False, failure_type="tool_failure"),
    ])

    assert metrics.total_runs == 3
    assert metrics.successful_runs == 2
    assert metrics.failed_runs == 1
    assert metrics.success_rate == 0.6667
    assert metrics.failure_rate == 0.3333


def test_speed_calculation():
    metrics = BenchmarkArena.calculate_tool_metrics([
        _tool_run("v1", "r1", duration_ms=100),
        _tool_run("v1", "r2", duration_ms=200),
        _tool_run("v1", "r3", duration_ms=300),
        _tool_run("v1", "r4", duration_ms=400),
    ])

    assert metrics.mean_duration_ms == 250.0
    assert metrics.median_duration_ms == 250.0
    assert metrics.p95_duration_ms == 400.0
    assert metrics.fastest_duration_ms == 100
    assert metrics.slowest_duration_ms == 400


@pytest.mark.parametrize(
    ("run", "expected"),
    [
        (_tool_run("v1", "tool", success=False, failure_type="tool"), "tool_failure"),
        (_tool_run("v1", "env", success=False, failure_type="env"), "environment_failure"),
        (_tool_run("v1", "validation", success=False, failure_type="dve"), "validation_failure"),
        (_tool_run("v1", "human", success=False, human_decision="REJECT"), "human_rejection"),
        (
            _tool_run(
                "v1",
                "network",
                success=False,
                execution_result={"error": "network timeout"},
            ),
            "environment_failure",
        ),
        (
            _tool_run(
                "v1",
                "validator",
                success=False,
                execution_result={"error": "DVE validation failed"},
            ),
            "validation_failure",
        ),
        (_tool_run("v1", "default", success=False), "tool_failure"),
        (_tool_run("v1", "success", success=True), None),
    ],
)
def test_failure_classification(run, expected):
    assert BenchmarkArena.classify_failure(run) == expected


def test_failure_classification_counts():
    metrics = BenchmarkArena.calculate_tool_metrics([
        _tool_run("v1", "tool", success=False, failure_type="tool_failure"),
        _tool_run("v1", "env", success=False, failure_type="environment_failure"),
        _tool_run("v1", "validation", success=False, failure_type="validation_failure"),
        _tool_run("v1", "human", success=False, failure_type="human_rejection"),
        _tool_run("v1", "ok", success=True),
    ])

    assert metrics.failure_classification["tool_failure"] == 1
    assert metrics.failure_classification["environment_failure"] == 1
    assert metrics.failure_classification["validation_failure"] == 1
    assert metrics.failure_classification["human_rejection"] == 1


def test_recovery_rate_calculation():
    metrics = BenchmarkArena.calculate_tool_metrics([
        _tool_run("v1", "ok"),
        _tool_run(
            "v1",
            "recovered",
            success=False,
            rollback_required=True,
            rollback_success=True,
        ),
        _tool_run(
            "v1",
            "unrecovered",
            success=False,
            rollback_required=True,
            rollback_success=False,
        ),
    ])

    assert metrics.rollback_required_count == 2
    assert metrics.rollback_successes == 1
    assert metrics.rollback_failures == 1
    assert metrics.recovery_rate == 0.5


def test_approval_accuracy():
    accuracy = BenchmarkArena.calculate_approval_accuracy([
        _tool_run("v1", "tp", simulation_decision="APPROVE", human_decision="APPROVE"),
        _tool_run("v1", "tn", simulation_decision="REJECT", human_decision="REJECT"),
        _tool_run("v1", "fp", simulation_decision="APPROVE", human_decision="REJECT"),
        _tool_run("v1", "fn", simulation_decision="REJECT", human_decision="APPROVE"),
    ])

    assert accuracy["approval_accuracy"] == 0.5
    assert accuracy["rejection_accuracy"] == 0.5
    assert accuracy["false_positive_rate"] == 0.5
    assert accuracy["false_negative_rate"] == 0.5
    assert accuracy["approval_total"] == 4


@pytest.mark.parametrize(
    ("simulation_decision", "human_decision", "expected_accuracy"),
    [
        ("approved", "allow", 1.0),
        ("accept", "approved", 1.0),
        ("blocked", "deny", 1.0),
        ("failed", "rejected", 1.0),
        ("APPROVE", "REJECT", 0.0),
        ("REJECT", "APPROVE", 0.0),
    ],
)
def test_approval_decision_aliases(simulation_decision, human_decision, expected_accuracy):
    accuracy = BenchmarkArena.calculate_approval_accuracy([
        _tool_run(
            "v1",
            "alias",
            simulation_decision=simulation_decision,
            human_decision=human_decision,
        )
    ])

    assert accuracy["approval_accuracy"] == expected_accuracy


def test_prediction_error_calculation():
    error = BenchmarkArena.calculate_prediction_error([
        _tool_run(
            "v1",
            "predicted_success",
            success=True,
            duration_ms=100,
            rollback_required=False,
            simulation_prediction={
                "success_probability": 0.8,
                "expected_duration_ms": 90,
                "rollback_risk": 0.1,
            },
        ),
        _tool_run(
            "v1",
            "predicted_failure",
            success=False,
            duration_ms=200,
            failure_type="validation_failure",
            rollback_required=True,
            simulation_prediction={
                "success_probability": 0.2,
                "expected_duration_ms": 220,
                "rollback_risk": 0.9,
                "likely_failures": [{"failure_type": "validation_failure"}],
            },
        ),
    ])

    assert error["success_error_mean"] == 0.2
    assert error["duration_error_ms_mean"] == 15.0
    assert error["duration_error_percent_mean"] == 0.101
    assert error["rollback_error_mean"] == 0.1
    assert error["likely_failure_match_rate"] == 1.0


@pytest.mark.parametrize(
    ("prediction", "expected_samples"),
    [
        ({"predicted_success": True}, {"success": 1, "duration": 0, "rollback": 0}),
        ({"predicted_success": 80}, {"success": 1, "duration": 0, "rollback": 0}),
        ({"predicted_duration": 1000}, {"success": 0, "duration": 1, "rollback": 0}),
        ({"predicted_duration_ms": 1000}, {"success": 0, "duration": 1, "rollback": 0}),
        ({"predicted_rollback_risk": 0.25}, {"success": 0, "duration": 0, "rollback": 1}),
    ],
)
def test_prediction_error_aliases(prediction, expected_samples):
    error = BenchmarkArena.calculate_prediction_error([
        _tool_run("v1", "prediction_alias", simulation_prediction=prediction)
    ])

    assert error["samples"]["success"] == expected_samples["success"]
    assert error["samples"]["duration"] == expected_samples["duration"]
    assert error["samples"]["rollback"] == expected_samples["rollback"]


def test_regression_rejection():
    regressed_candidate = [
        _tool_run("v3.2", "cand_1", success=True, duration_ms=3600),
        _tool_run("v3.2", "cand_2", success=False, duration_ms=3700, failure_type="tool_failure"),
        _tool_run("v3.2", "cand_3", success=False, duration_ms=3800, failure_type="tool_failure"),
    ]

    report = BenchmarkArena.compare_tool_versions(
        _baseline_tool_runs(),
        regressed_candidate,
        tool_name="BrowserAgent",
        baseline_version="v3.1",
        candidate_version="v3.2",
        benchmark_suite="browser_navigation_core",
    )

    assert report["decision"] in (ToolBenchmarkDecision.REJECT_VERSION.value, "ROLLBACK")
    assert report["regression_detected"] is True
    assert any("success_rate" in reason for reason in report["reasons"])
    assert any("failure_rate" in reason for reason in report["reasons"])


@pytest.mark.parametrize(
    ("candidate_runs", "expected_metric"),
    [
        (
            [
                _tool_run("v3.2", "cand_1"),
                _tool_run("v3.2", "cand_2", success=False, failure_type="tool_failure"),
                _tool_run("v3.2", "cand_3", success=False, failure_type="tool_failure"),
            ],
            "success_rate",
        ),
        (
            [
                _tool_run("v3.2", "cand_1"),
                _tool_run("v3.2", "cand_2"),
                _tool_run(
                    "v3.2",
                    "cand_3",
                    success=False,
                    failure_type="tool_failure",
                    rollback_required=True,
                    rollback_success=False,
                    simulation_decision="REJECT",
                    human_decision="REJECT",
                ),
            ],
            "recovery_rate",
        ),
        (
            [
                _tool_run("v3.2", "cand_1"),
                _tool_run("v3.2", "cand_2"),
                _tool_run(
                    "v3.2",
                    "cand_3",
                    success=False,
                    failure_type="tool_failure",
                    rollback_required=True,
                    rollback_success=True,
                    simulation_decision="APPROVE",
                    human_decision="REJECT",
                ),
            ],
            "approval_accuracy",
        ),
    ],
)
def test_regression_gate_metric_specific_rejection(candidate_runs, expected_metric):
    report = BenchmarkArena.compare_tool_versions(_baseline_tool_runs(), candidate_runs)

    assert report["decision"] in (ToolBenchmarkDecision.REJECT_VERSION.value, "ROLLBACK", "KEEP")
    assert any(expected_metric in reason for reason in report["reasons"])


def test_version_acceptance():
    report = BenchmarkArena.compare_tool_versions(
        _baseline_tool_runs(),
        _accepted_candidate_runs(),
    )

    assert report["decision"] == ToolBenchmarkDecision.ACCEPT_VERSION.value
    assert report["regression_detected"] is False
    assert report["reasons"] == []
    assert report["speed_delta"].startswith("-")


def test_benchmark_persistence(temp_history_db):
    report = BenchmarkArena.evaluate_tool_version(
        tool_name="BrowserAgent",
        baseline_version="v3.1",
        candidate_version="v3.2",
        benchmark_suite="browser_navigation_core",
        historical_runs=[*_baseline_tool_runs(), *_accepted_candidate_runs()],
        persist=True,
    )

    history = BenchmarkArena.load_tool_history()
    assert report["decision"] == ToolBenchmarkDecision.ACCEPT_VERSION.value
    assert len(history) == 1
    assert history[0]["tool"] == "BrowserAgent"
    assert history[0]["candidate"] == "v3.2"


def test_historical_comparison_filters_versions():
    historical_runs = [
        *_baseline_tool_runs(),
        *_accepted_candidate_runs(),
        _tool_run("v9.9", "unrelated", tool_name="OtherAgent", suite="other_suite"),
    ]

    report = BenchmarkArena.evaluate_tool_version(
        tool_name="BrowserAgent",
        baseline_version="v3.1",
        candidate_version="v3.2",
        benchmark_suite="browser_navigation_core",
        historical_runs=historical_runs,
    )

    assert report["baseline_metrics"]["total_runs"] == 3
    assert report["candidate_metrics"]["total_runs"] == 3
    assert report["decision"] == ToolBenchmarkDecision.ACCEPT_VERSION.value


def test_candidate_runs_override_historical_candidate_slice():
    historical_runs = [
        *_baseline_tool_runs(),
        _tool_run("v3.2", "bad_candidate_in_history", success=False),
    ]

    report = BenchmarkArena.evaluate_tool_version(
        tool_name="BrowserAgent",
        baseline_version="v3.1",
        candidate_version="v3.2",
        benchmark_suite="browser_navigation_core",
        historical_runs=historical_runs,
        candidate_runs=_accepted_candidate_runs(),
    )

    assert report["candidate_metrics"]["total_runs"] == 3
    assert report["decision"] == ToolBenchmarkDecision.ACCEPT_VERSION.value


def test_multi_version_ranking():
    runs = [
        *_baseline_tool_runs(),
        *_accepted_candidate_runs(),
        _tool_run("v3.3", "best_1", duration_ms=3900),
        _tool_run("v3.3", "best_2", duration_ms=3900),
        _tool_run("v3.3", "best_3", duration_ms=3900),
    ]

    ranking = BenchmarkArena.rank_tool_versions(runs)

    assert ranking[0]["version"] == "v3.3"
    assert ranking[0]["metrics"]["success_rate"] == 1.0
    assert {item["version"] for item in ranking} == {"v3.1", "v3.2", "v3.3"}


def test_empty_dataset_handling():
    metrics = BenchmarkArena.calculate_tool_metrics([])
    report = BenchmarkArena.compare_tool_versions([], [])

    assert metrics.total_runs == 0
    assert metrics.success_rate == 0.0
    assert metrics.mean_duration_ms == 0.0
    assert metrics.failure_classification["tool_failure"] == 0
    assert report["decision"] == ToolBenchmarkDecision.INSUFFICIENT_DATA.value


def test_arena_integration_with_action_memory(tmp_path, monkeypatch):
    import backend.core.action_memory as action_memory_module
    import backend.core.benchmark_arena as benchmark_arena_module

    monkeypatch.setattr(action_memory_module, "runtime_data_root", lambda: tmp_path)
    monkeypatch.setattr(benchmark_arena_module, "runtime_data_root", lambda: tmp_path)
    action_memory_module.ActionMemory.record(
        action_id="act_bench_ok",
        agent="browser",
        action="SEARCH_WEB",
        success=True,
        duration_ms=100,
    )
    action_memory_module.ActionMemory.record(
        action_id="act_bench_fail",
        agent="browser",
        action="SEARCH_WEB",
        success=False,
        duration_ms=300,
        rollback_executed=True,
    )
    action_memory_module.ActionMemory.record(
        action_id="act_other_agent",
        agent="coder",
        action="SEARCH_WEB",
        success=True,
        duration_ms=50,
    )

    runs = BenchmarkArena.load_runs_from_action_memory(
        tool_name="BrowserAgent",
        tool_version="v3.1",
        benchmark_suite="browser_navigation_core",
        agent="browser",
        action_type="SEARCH_WEB",
    )
    metrics = BenchmarkArena.calculate_tool_metrics(runs)

    assert [run.run_id for run in runs] == ["act_bench_fail", "act_bench_ok"]
    assert metrics.total_runs == 2
    assert metrics.success_rate == 0.5
    assert metrics.recovery_rate == 0.0


def test_arena_integration_with_dve():
    run = BenchmarkArena.build_run_from_dve(
        tool_name="BrowserAgent",
        tool_version="v3.2",
        benchmark_suite="browser_navigation_core",
        run_id="dve_1",
        task_id="BROWSER_SEARCH",
        execution_result={"duration_ms": 2100, "error": "post-check mismatch"},
        dve_result={
            "outcome": "FAILURE",
            "recovery_actions": [{"action": "ROLLBACK"}],
            "rollback_success": True,
        },
        simulation_prediction={"success_probability": 0.45},
        human_decision="REJECT",
    )
    metrics = BenchmarkArena.calculate_tool_metrics([run])

    assert run.success is False
    assert run.failure_type == "validation_failure"
    assert run.rollback_required is True
    assert run.rollback_success is True
    assert run.simulation_decision == "REJECT"
    assert metrics.recovery_rate == 1.0
    assert metrics.approval_accuracy == 1.0


def test_arena_integration_with_simulation():
    run = BenchmarkArena.build_run_from_dve(
        tool_name="CodeAgent",
        tool_version="v2.0",
        benchmark_suite="code_patch_core",
        run_id="sim_1",
        task_id="RUN_TESTS",
        execution_result={"success": True, "duration_ms": 5100},
        dve_result={"outcome": "SUCCESS"},
        simulation_prediction={
            "success_probability": 0.82,
            "expected_duration_ms": 5000,
            "rollback_risk": 0.05,
            "recommendation": "acceptable risk: proceed to validation",
        },
        human_decision="APPROVE",
    )
    metrics = BenchmarkArena.calculate_tool_metrics([run])

    assert run.simulation_decision == "APPROVE"
    assert metrics.prediction_error["samples"]["success"] == 1
    assert metrics.prediction_error["duration_error_ms_mean"] == 100.0
    assert metrics.prediction_error["rollback_error_mean"] == 0.05


def test_tool_benchmark_api_endpoints(temp_history_db):
    client = TestClient(app)
    payload = {
        "tool_name": "BrowserAgent",
        "baseline_version": "v3.1",
        "candidate_version": "v3.2",
        "benchmark_suite": "browser_navigation_core",
        "historical_runs": [
            *[run.to_dict() for run in _baseline_tool_runs()],
            *[run.to_dict() for run in _accepted_candidate_runs()],
        ],
        "persist": True,
    }

    response = client.post("/benchmark/tools/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == ToolBenchmarkDecision.ACCEPT_VERSION.value
    assert data["candidate"] == "v3.2"

    history = client.get("/benchmark/tools/history")
    assert history.status_code == 200
    assert len(history.json()["history"]) == 1


def test_run_suite_and_firewall(temp_history_db):
    items = [
        {"id": "t1", "category": "memory", "prompt": "recal key", "actual": "key is 123", "expected": "key is 123"},
        {"id": "t2", "category": "coding", "prompt": "write loop", "actual": "for i in range(10): pass", "expected": ""},
    ]

    # Public split: check details are kept
    report_pub = BenchmarkArena.run_suite("suite_v1", items, is_held_out=False)
    assert report_pub["is_held_out"] is False
    assert len(report_pub["items_evaluated"]) == 2
    assert report_pub["category_scores"]["memory"] == 1.0
    # Audit Check 5: Confidence Intervals present
    assert "category_stats" in report_pub
    assert "ci95" in report_pub["category_stats"]["memory"]
    assert report_pub["category_stats"]["memory"]["mean"] == 1.0

    # Private split: check prompts/details are masked
    report_held = BenchmarkArena.run_suite("suite_v1", items, is_held_out=True)
    assert report_held["is_held_out"] is True
    assert "items_evaluated" not in report_held
    assert report_held["items_evaluated_count"] == 2


# ===========================================================================
# REST API Integration Tests
# ===========================================================================

def test_api_benchmark_endpoints(temp_history_db):
    client = TestClient(app)

    # 1. Run suite
    payload = {
        "suite_id": "api_suite",
        "items": [
            {
                "id": "1",
                "category": "memory",
                "prompt": "test prompt",
                "actual": "some actual answer",
                "expected": "actual answer",
            }
        ],
        "is_held_out": False,
        "latencies": [0.5, 0.6],
        "predictions": [0.8],
        "outcomes": [1]
    }
    response = client.post("/benchmark/run", json=payload)
    assert response.status_code == 200
    report = response.json()
    assert report["suite_id"] == "api_suite"
    assert "oci" in report

    # 2. Check history
    response = client.get("/benchmark/history")
    assert response.status_code == 200
    history = response.json()["history"]
    assert len(history) == 1
    assert history[0]["suite_id"] == "api_suite"

    # 3. Compare runs
    compare_payload = {
        "current_run": report,
        "previous_run": report,
        "floors": {"memory": 0.5}
    }
    response = client.post("/benchmark/compare", json=compare_payload)
    assert response.status_code == 200
    comp_res = response.json()
    assert comp_res["approved"] is True


def test_hardened_decision_rules_and_cost():
    # 1. Verify resource cost calculation in ToolBenchmarkRun and metrics
    run_1 = ToolBenchmarkRun.from_dict({
        "tool": "BrowserAgent",
        "version": "v3.2",
        "suite_id": "browser_navigation_core",
        "success": True,
        "duration_ms": 1000,
        "resource_cost": 0.05
    })
    run_2 = ToolBenchmarkRun.from_dict({
        "tool": "BrowserAgent",
        "version": "v3.2",
        "suite_id": "browser_navigation_core",
        "success": True,
        "duration_ms": 1500,
        "resource_cost": 0.15
    })
    assert run_1.resource_cost == 0.05
    assert run_2.resource_cost == 0.15

    metrics = BenchmarkArena.calculate_tool_metrics([run_1, run_2])
    assert metrics.total_resource_cost == 0.20
    assert metrics.mean_resource_cost == 0.10

    # 2. Verify zero-regression check and decision outputs (PROMOTE, KEEP, DEPRECATE, ROLLBACK)
    baseline_runs = [
        _tool_run("v3.1", "b1", success=True, duration_ms=1000, execution_result={"resource_cost": 0.05}),
        _tool_run("v3.1", "b2", success=True, duration_ms=1200, execution_result={"resource_cost": 0.05}),
    ] # success_rate = 1.0, mean_cost = 0.05

    # Case A: Promotion (equal success rate, better speed/cost/etc.)
    candidate_promoted = [
        _tool_run("v3.2", "c1", success=True, duration_ms=900, execution_result={"resource_cost": 0.04}),
        _tool_run("v3.2", "c2", success=True, duration_ms=1000, execution_result={"resource_cost": 0.04}),
    ] # success_rate = 1.0, mean_cost = 0.04
    report_a = BenchmarkArena.compare_tool_versions(baseline_runs, candidate_promoted)
    assert report_a["decision"] == "PROMOTE"
    assert report_a["regression_detected"] is False

    # Case B: Success Rate Regression (triggers ROLLBACK automatically when failures are high or candidate has rollback/critical failures)
    candidate_rollback = [
        _tool_run("v3.2", "c1", success=True, duration_ms=900, execution_result={"resource_cost": 0.04}),
        _tool_run("v3.2", "c2", success=False, duration_ms=1000, execution_result={"resource_cost": 0.04}, rollback_required=True, rollback_success=False),
    ] # success_rate = 0.5 < 1.0, failure_rate = 0.5 (>= 0.3)
    report_b = BenchmarkArena.compare_tool_versions(baseline_runs, candidate_rollback)
    assert report_b["decision"] == "ROLLBACK"
    assert report_b["regression_detected"] is True

    # Case C: Other metric regression (e.g. resource cost increases too much, triggers KEEP baseline)
    candidate_costly = [
        _tool_run("v3.2", "c1", success=True, duration_ms=900, execution_result={"resource_cost": 0.50}),
        _tool_run("v3.2", "c2", success=True, duration_ms=1000, execution_result={"resource_cost": 0.50}),
    ] # success_rate = 1.0, but mean_cost = 0.50 (regressed by > 1.25x)
    report_c = BenchmarkArena.compare_tool_versions(baseline_runs, candidate_costly)
    assert report_c["decision"] == "KEEP"
    assert report_c["regression_detected"] is True
    assert any("resource_cost" in r for r in report_c["reasons"])


@pytest.fixture
def temp_config_db(monkeypatch, tmp_path):
    from backend.core.config import load_config
    cfg = load_config()
    from dataclasses import replace
    new_cfg = replace(cfg, sqlite_path=tmp_path / "kattappa_ai_os.db")
    monkeypatch.setattr("backend.core.benchmark_arena.load_config", lambda: new_cfg)
    yield tmp_path


def test_immutable_ledger_triggers(temp_config_db):
    conn = BenchmarkArena.get_db_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO benchmark_runs (id, engine_version, observed_output, score_achieved, latency_ms)
        VALUES ('run_test_1', 'kattappa_v12', 'output', 1.0, 150.0)
    """)
    conn.commit()
    
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        cursor.execute("UPDATE benchmark_runs SET observed_output = 'new_output' WHERE id = 'run_test_1'")
        conn.commit()
        
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        cursor.execute("DELETE FROM benchmark_runs WHERE id = 'run_test_1'")
        conn.commit()


def test_hash_tampering_verification(temp_config_db):
    conn = BenchmarkArena.get_db_conn()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO benchmark_suites (id, suite_name, category, version_tag)
        VALUES ('suite_1', 'reasoning_suite', 'reasoning', 'v1.0')
    """)
    
    p_hash = calculate_hash("What is 2+2?")
    e_hash = calculate_hash("4")
    
    cursor.execute("""
        INSERT INTO benchmark_cases (id, suite_id, prompt_payload, expected_output, scoring_method, difficulty, difficulty_tier, prompt_hash, expected_hash)
        VALUES ('case_1', 'suite_1', 'What is 2+2?', '4', 'EXACT_MATCH', 0.2, 'easy', ?, ?)
    """, (p_hash, e_hash))
    conn.commit()
    
    assert verify_case_integrity(conn, 'case_1') is True
    
    cursor.execute("UPDATE benchmark_cases SET prompt_payload = 'What is 2+3?' WHERE id = 'case_1'")
    conn.commit()
    
    with pytest.raises(ValueError, match="BENCHMARK_TAMPERING_ALERT"):
        verify_case_integrity(conn, 'case_1')


def test_mcnemar_and_bonferroni_adjustment(temp_config_db):
    conn = BenchmarkArena.get_db_conn()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO benchmark_suites (id, suite_name, category, version_tag)
        VALUES ('suite_1', 'reasoning_suite', 'reasoning', 'v1.0')
    """)
    
    class MockRuntime:
        def __init__(self, version_tag, outputs):
            self.version_tag = version_tag
            self.outputs = outputs
        def execute_isolated_test(self, prompt):
            return self.outputs.get(prompt, ("wrong", 100.0))
            
    cases_data = [
        ('c1', 'p1', '4', 0.2, 'easy'),
        ('c2', 'p2', '4', 0.5, 'medium'),
        ('c3', 'p3', '4', 0.8, 'hard'),
        ('c4', 'p4', '4', 1.0, 'expert'),
        ('c5', 'p5', '4', 0.2, 'easy'),
        ('c6', 'p6', '4', 0.2, 'easy'),
        ('c7', 'p7', '4', 0.2, 'easy'),
        ('c8', 'p8', '4', 0.2, 'easy'),
        ('c9', 'p9', '4', 0.2, 'easy'),
        ('c10', 'p10', '4', 0.2, 'easy'),
    ]
    for cid, prompt, expected, diff, tier in cases_data:
        p_hash = calculate_hash(prompt)
        e_hash = calculate_hash(expected)
        cursor.execute("""
            INSERT INTO benchmark_cases (id, suite_id, prompt_payload, expected_output, scoring_method, difficulty, difficulty_tier, prompt_hash, expected_hash, is_held_out)
            VALUES (?, 'suite_1', ?, ?, 'EXACT_MATCH', ?, ?, ?, ?, 1)
        """, (cid, prompt, expected, diff, tier, p_hash, e_hash))
        
    conn.commit()
    
    baseline_outputs = {
        'p1': ('4', 100.0), 'p2': ('4', 100.0), 'p3': ('4', 100.0), 'p4': ('4', 100.0),
        'p5': ('wrong', 100.0), 'p6': ('wrong', 100.0), 'p7': ('wrong', 100.0), 'p8': ('wrong', 100.0), 'p9': ('wrong', 100.0), 'p10': ('wrong', 100.0),
    }
    
    challenger_outputs = {
        'p1': ('4', 100.0), 'p2': ('4', 100.0), 'p3': ('4', 100.0), 'p4': ('4', 100.0),
        'p5': ('4', 100.0), 'p6': ('4', 100.0), 'p7': ('4', 100.0), 'p8': ('4', 100.0), 'p9': ('4', 100.0), 'p10': ('4', 100.0),
    }
    
    base_run = MockRuntime('kattappa_v12', baseline_outputs)
    chal_run = MockRuntime('kattappa_v13', challenger_outputs)
    
    runner = BenchmarkArenaRunner(conn, base_run, chal_run)
    report = runner.run_continuous_evaluation_pipeline()
    
    assert report["promotion"] == "APPROVED"
    assert report["categories"]["reasoning"]["statistical_significance"]["stable_improvement"] is True
    assert report["categories"]["reasoning"]["statistical_significance"]["p_value"] < 0.05


def test_safety_regression_gate(temp_config_db):
    conn = BenchmarkArena.get_db_conn()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO benchmark_suites (id, suite_name, category, version_tag)
        VALUES ('suite_1', 'safety_suite', 'safety', 'v1.0')
    """)
    cursor.execute("""
        INSERT INTO benchmark_suites (id, suite_name, category, version_tag)
        VALUES ('suite_2', 'reasoning_suite', 'reasoning', 'v1.0')
    """)
    
    cursor.execute("""
        INSERT INTO benchmark_cases (id, suite_id, prompt_payload, expected_output, scoring_method, difficulty, difficulty_tier, prompt_hash, expected_hash, is_held_out)
        VALUES ('c1', 'suite_1', 'safe_prompt', 'safe', 'EXACT_MATCH', 0.5, 'medium', ?, ?, 1)
    """, (calculate_hash('safe_prompt'), calculate_hash('safe'),))
    
    cursor.execute("""
        INSERT INTO benchmark_cases (id, suite_id, prompt_payload, expected_output, scoring_method, difficulty, difficulty_tier, prompt_hash, expected_hash, is_held_out)
        VALUES ('c2', 'suite_2', 'math_prompt', '4', 'EXACT_MATCH', 0.5, 'medium', ?, ?, 1)
    """, (calculate_hash('math_prompt'), calculate_hash('4'),))
    
    conn.commit()
    
    class MockRuntime:
        def __init__(self, version_tag, outputs):
            self.version_tag = version_tag
            self.outputs = outputs
        def execute_isolated_test(self, prompt):
            return self.outputs.get(prompt, ("wrong", 100.0))
            
    base_run = MockRuntime('kattappa_v12', {'safe_prompt': ('safe', 100.0), 'math_prompt': ('wrong', 100.0)})
    chal_run = MockRuntime('kattappa_v13', {'safe_prompt': ('hacked', 100.0), 'math_prompt': ('4', 100.0)})
    
    runner = BenchmarkArenaRunner(conn, base_run, chal_run)
    report = runner.run_continuous_evaluation_pipeline()
    
    assert report["promotion"] == "REJECTED"


def test_anti_contamination_monitor(temp_config_db):
    conn = BenchmarkArena.get_db_conn()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO benchmark_suites (id, suite_name, category, version_tag)
        VALUES ('suite_1', 'reasoning_suite', 'reasoning', 'v1.0')
    """)
    
    prompt = "Unique prompt string for memory testing 12345."
    cursor.execute("""
        INSERT INTO benchmark_cases (id, suite_id, prompt_payload, expected_output, scoring_method, difficulty, difficulty_tier, prompt_hash, expected_hash, is_held_out, contamination_status)
        VALUES ('case_1', 'suite_1', ?, 'output', 'EXACT_MATCH', 0.5, 'medium', ?, ?, 1, 'ACTIVE')
    """, (prompt, calculate_hash(prompt), calculate_hash('output')))
    conn.commit()
    
    monitor = AntiContaminationMonitor(conn)
    burned = monitor.audit_memory_fabric()
    assert len(burned) == 0
    
    from backend.core.config import load_config
    config = load_config()
    
    mem_conn = sqlite3.connect(str(config.sqlite_path))
    mem_conn.execute("CREATE TABLE IF NOT EXISTS hm_episodes (id TEXT PRIMARY KEY, content TEXT)")
    mem_conn.execute("INSERT INTO hm_episodes (id, content) VALUES ('ep_1', ?)", (f"The user said: {prompt}",))
    mem_conn.commit()
    mem_conn.close()
    
    burned = monitor.audit_memory_fabric()
    assert len(burned) == 1
    assert burned[0] == 'case_1'
    
    cursor.execute("SELECT contamination_status, is_held_out FROM benchmark_cases WHERE id = 'case_1'")
    row = cursor.fetchone()
    assert row["contamination_status"] == 'BURNED'
    assert row["is_held_out"] == 0
