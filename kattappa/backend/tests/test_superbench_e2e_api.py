from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.core.superbench_engine import SuperbenchEngine
from backend.main import app


def test_api_defaults_to_isolated_memory_and_persists_identity(superbench_storage) -> None:
    SuperbenchEngine.generate_benchmark_tasks()
    with patch(
        "backend.core.superbench_engine.SuperbenchEngine._execute_runtime",
        return_value={"response": "verified", "trace": []},
    ):
        response = TestClient(app).post("/api/v1/superbench/run/SB_TASK_0501", json={})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "succeeded"
    assert result["memory_mode"] == "isolated"
    persisted = TestClient(app).get(f"/api/v1/superbench/runs/{result['run_id']}")
    assert persisted.status_code == 200
    assert persisted.json()["trace_id"] == result["trace_id"]


def test_production_memory_requires_explicit_authorization(superbench_storage) -> None:
    SuperbenchEngine.generate_benchmark_tasks()
    response = TestClient(app).post(
        "/api/v1/superbench/run/SB_TASK_0501",
        json={"memory_mode": "production"},
    )
    assert response.status_code == 403
