from __future__ import annotations

from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import hashlib

import pytest

from backend.core.superbench_engine import SuperbenchEngine


@pytest.fixture
def superbench_storage(tmp_path, monkeypatch):
    import backend.core.superbench_engine as engine_module

    monkeypatch.setattr(engine_module, "runtime_data_root", lambda: tmp_path)
    SuperbenchEngine._schema_path = None
    yield tmp_path
    SuperbenchEngine._schema_path = None


def test_sb_task_0501_runs_three_times_without_shared_workspace(superbench_storage) -> None:
    SuperbenchEngine.generate_benchmark_tasks()
    with patch(
        "backend.core.superbench_engine.SuperbenchEngine._execute_runtime",
        return_value={"response": "verified", "trace": []},
    ):
        results = [SuperbenchEngine.execute_task("SB_TASK_0501") for _ in range(3)]
    assert {result["status"] for result in results} == {"succeeded"}
    assert len({result["run_id"] for result in results}) == 3
    assert len({result["workspace_id"] for result in results}) == 3
    assert len({result["trace_id"] for result in results}) == 3


def test_vector_disabled_is_explicitly_degraded(superbench_storage) -> None:
    SuperbenchEngine.generate_benchmark_tasks()
    with patch(
        "backend.core.superbench_engine.SuperbenchEngine._execute_runtime",
        return_value={"response": "verified", "trace": []},
    ):
        result = SuperbenchEngine.execute_task("SB_TASK_0501", vector_enabled=False)
    assert result["status"] == "degraded"
    assert result["memory_backend"] == "keyword_fallback"


def test_isolated_run_never_changes_production_memory(superbench_storage) -> None:
    production = superbench_storage / "production-memory.db"
    production.write_bytes(b"authoritative-production-state")
    before = hashlib.sha256(production.read_bytes()).hexdigest()
    SuperbenchEngine.generate_benchmark_tasks()
    with patch(
        "backend.core.superbench_engine.SuperbenchEngine._execute_runtime",
        return_value={"response": "verified", "trace": []},
    ):
        SuperbenchEngine.execute_task("SB_TASK_0501")
    assert hashlib.sha256(production.read_bytes()).hexdigest() == before


def test_two_concurrent_benchmarks_have_distinct_mutable_state(superbench_storage) -> None:
    SuperbenchEngine.generate_benchmark_tasks()
    with patch(
        "backend.core.superbench_engine.SuperbenchEngine._execute_runtime",
        return_value={"response": "verified", "trace": []},
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(SuperbenchEngine.execute_task, ("SB_TASK_0501", "SB_TASK_0501")))
    assert results[0]["run_id"] != results[1]["run_id"]
    roots = [superbench_storage / "superbench" / "runs" / result["run_id"] for result in results]
    assert roots[0] != roots[1]
    assert all(root.exists() for root in roots)


def test_completed_run_survives_engine_schema_reset(superbench_storage) -> None:
    SuperbenchEngine.generate_benchmark_tasks()
    with patch(
        "backend.core.superbench_engine.SuperbenchEngine._execute_runtime",
        return_value={"response": "verified", "trace": []},
    ):
        result = SuperbenchEngine.execute_task("SB_TASK_0501")
    SuperbenchEngine._schema_path = None
    persisted = SuperbenchEngine.get_run(result["run_id"])
    assert persisted is not None
    assert persisted["trace_id"] == result["trace_id"]


def test_statistics_aggregate_canonical_run_records(superbench_storage) -> None:
    SuperbenchEngine.generate_benchmark_tasks()
    with patch(
        "backend.core.superbench_engine.SuperbenchEngine._execute_runtime",
        return_value={"response": "verified", "trace": []},
    ):
        result = SuperbenchEngine.execute_task("SB_TASK_0501")

    stats = SuperbenchEngine.get_statistics()

    assert result["status"] == "succeeded"
    assert stats["total_executed"] == 1
    assert stats["success_count"] == 0
    assert stats["rejected_count"] == 1
    assert stats["category_stats"]["Security"]["success"] == 1
