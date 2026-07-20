from __future__ import annotations

from unittest.mock import patch

from backend.core.superbench_engine import SuperbenchEngine


def test_vector_failure_returns_structured_degraded_contract(superbench_storage) -> None:
    SuperbenchEngine.generate_benchmark_tasks()
    with patch(
        "backend.core.superbench_engine.SuperbenchEngine._execute_runtime",
        return_value={"response": "safe", "trace": []},
    ):
        result = SuperbenchEngine.execute_task(
            "SB_TASK_0501", simulate_vector_failure=True
        )
    assert result["status"] == "degraded"
    assert result["memory_mode"] == "isolated"
    assert result["memory_backend"] == "keyword_fallback"
    assert result["failure_category"] == "VECTOR_INDEX_LOAD_FAILURE"
    assert result["trace_id"].startswith("sb_trace_")
    assert result["warnings"]


def test_runtime_timeout_returns_structured_retryable_failure(superbench_storage) -> None:
    SuperbenchEngine.generate_benchmark_tasks()
    with patch(
        "backend.core.superbench_engine.SuperbenchEngine._execute_runtime",
        side_effect=TimeoutError("isolated worker exceeded 30 seconds"),
    ):
        result = SuperbenchEngine.execute_task("SB_TASK_0001")

    assert result["status"] == "failed"
    assert result["failure_category"] == "RUNTIME_TIMEOUT"
    assert result["retry_eligible"] is True
    assert result["exception_fingerprint"]
