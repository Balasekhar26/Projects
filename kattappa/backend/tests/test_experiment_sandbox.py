from __future__ import annotations

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.experiment_sandbox import ExperimentManager


def test_experiment_sandbox_success_flow(monkeypatch):
    # 1. Successful sandbox run (status PASS)
    report = ExperimentManager.execute_experiment(
        proposal_id="p-safe-opt",
        baseline_benchmarks={
            "latency_ms": 10.0,
            "cpu_usage_pct": 15.0,
            "memory_mb": 40.0,
            "reliability_score": 0.98,
            "safety_score": 1.0,
        }
    )

    assert report["proposal_id"] == "p-safe-opt"
    assert report["status"] == "PASS"
    assert report["protected_core_touched"] is False
    assert report["tests"]["pass_rate"] == 1.0
    assert report["benchmarks"]["performance_gain"] > 0.0
    assert report["validation"]["validation_passed"] is True
    assert len(report["regressions"]) == 0
    assert report["recommendation"] == "NEEDS_REVIEW"
    assert report["confidence"] == 0.92


def test_experiment_sandbox_regression_flow():
    # 2. Regression run (status FAIL)
    report = ExperimentManager.execute_experiment(
        proposal_id="p-regression-opt",
        mock_regression=True
    )

    assert report["status"] == "FAIL"
    assert len(report["regressions"]) > 0
    assert any("Test failure" in r or "Performance Gain" in r for r in report["regressions"])
    assert report["recommendation"] == "REJECT"
    assert report["confidence"] == 0.50


def test_experiment_sandbox_protected_core_block():
    # 3. Protected Core violation (status FAIL, touches_protected_core=True)
    report = ExperimentManager.execute_experiment(
        proposal_id="p-unsafe-proposal_governance",
        baseline_benchmarks=None,
    )
    # The title "p-unsafe-governance" has "governance" in it which is a protected core module keyword,
    # so it should trigger a core violation.
    assert report["status"] == "FAIL"
    assert report["protected_core_touched"] is True
    assert any("Protected Core" in r for r in report["regressions"])
    assert report["recommendation"] == "REJECT"


def test_experiment_sandbox_cleanup_on_crash():
    # Verify that the sandbox cleanup happens even if execution crashes.
    # We will hook into the workspace path logging to trace the directory
    import tempfile
    original_mkdtemp = tempfile.mkdtemp
    created_dirs = []

    def mock_mkdtemp(*args, **kwargs):
        res = original_mkdtemp(*args, **kwargs)
        created_dirs.append(res)
        return res

    import tempfile as tf
    tf.mkdtemp = mock_mkdtemp

    try:
        # Trigger an execution crash in the manager
        with pytest.raises(Exception):
            ExperimentManager.execute_experiment(
                proposal_id="p-crash",
                mock_crash=True
            )
        
        # Verify that the created folder does not exist anymore
        assert len(created_dirs) == 1
        path = Path(created_dirs[0])
        assert not path.exists()

    finally:
        tf.mkdtemp = original_mkdtemp


def test_experiment_sandbox_api():
    client = TestClient(app)
    
    payload = {
        "baseline_benchmarks": {
            "latency_ms": 20.0,
            "cpu_usage_pct": 30.0,
            "memory_mb": 60.0,
            "reliability_score": 0.98,
            "safety_score": 1.0
        },
        "mock_regression": False,
        "mock_crash": False
    }

    response = client.post("/sandbox/run-experiment-v2/p-api-run", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    
    report = res_data["report"]
    assert report["proposal_id"] == "p-api-run"
    assert report["status"] == "PASS"
    assert "benchmarks" in report
    assert "validation" in report
