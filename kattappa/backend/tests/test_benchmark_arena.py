from __future__ import annotations

import os
import sqlite3
import pytest
import tempfile
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.benchmark_arena import BenchmarkArena, BenchmarkCategory


@pytest.fixture
def temp_history_db(monkeypatch):
    """Sets a temporary folder for benchmark history so tests don't write to primary logs."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_benchmark_test_")
    monkeypatch.setattr("backend.core.benchmark_arena.runtime_data_root", lambda: Path(temp_dir))
    from pathlib import Path
    yield Path(temp_dir)
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


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
