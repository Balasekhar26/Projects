"""Tests for relative Action Runtime benchmark statistics."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.action.benchmark import ActionBenchmarkConfig, ActionRuntimeBenchmark

pytestmark = [pytest.mark.integration, pytest.mark.performance]


def test_benchmark_excludes_warmups_and_builds_rolling_baseline(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    history = tmp_path / "history.json"
    config = ActionBenchmarkConfig(
        warmup_runs=2, sample_runs=5, regression_tolerance=1.0
    )
    benchmark = ActionRuntimeBenchmark(workspace, config=config)

    first = benchmark.run(history)
    benchmark.record(first, history)
    second = benchmark.run(history)

    assert len(first.samples_ms) == 5
    assert first.baseline_median_ms is None
    assert first.false_success_count == 0
    assert first.successful_runs == 5
    assert second.baseline_median_ms == pytest.approx(first.median_latency_ms)
    assert second.regression_ratio is not None
    assert second.memory_passed is True


@pytest.mark.parametrize("sample_runs", [0, 2, 4])
def test_benchmark_rejects_non_median_sample_sizes(sample_runs: int) -> None:
    with pytest.raises(ValueError):
        ActionBenchmarkConfig(sample_runs=sample_runs)
