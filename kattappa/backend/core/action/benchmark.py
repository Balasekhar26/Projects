"""Repeatable relative benchmark harness for the Action Runtime."""

from __future__ import annotations

import json
import platform
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from backend.core.action.capabilities import Capability, CapabilityManager
from backend.core.action.file_executor import FileExecutor
from backend.core.action.models import Action
from backend.core.action.registry import ExecutorRegistry
from backend.core.action.verifier import FileVerifier


@dataclass(frozen=True, slots=True)
class ActionBenchmarkConfig:
    """Configuration for warm-up, sampling, regression, and memory gates."""

    warmup_runs: int = 3
    sample_runs: int = 11
    regression_tolerance: float = 0.15
    memory_ceiling_mb: float = 8192.0
    rolling_window: int = 10

    def __post_init__(self) -> None:
        """Reject configurations that would produce misleading statistics."""

        if self.warmup_runs < 0:
            raise ValueError("warmup_runs must not be negative")
        if self.sample_runs < 3 or self.sample_runs % 2 == 0:
            raise ValueError("sample_runs must be an odd integer of at least 3")
        if not 0 <= self.regression_tolerance <= 1:
            raise ValueError("regression_tolerance must be between 0 and 1")
        if self.memory_ceiling_mb <= 0:
            raise ValueError("memory_ceiling_mb must be positive")
        if self.rolling_window < 1:
            raise ValueError("rolling_window must be positive")


@dataclass(frozen=True, slots=True)
class ActionBenchmarkResult:
    """Serializable benchmark measurements and acceptance decisions."""

    samples_ms: tuple[float, ...]
    median_latency_ms: float
    baseline_median_ms: float | None
    regression_ratio: float | None
    regression_tolerance: float
    regression_passed: bool
    successful_runs: int
    false_success_count: int
    peak_memory_mb: float
    memory_ceiling_mb: float
    memory_passed: bool
    passed: bool
    platform_key: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        data = asdict(self)
        data["samples_ms"] = list(self.samples_ms)
        return data


class ActionRuntimeBenchmark:
    """Measure the canonical file pipeline after excluded warm-up executions."""

    def __init__(
        self,
        workspace: str | Path,
        config: ActionBenchmarkConfig | None = None,
        process: psutil.Process | None = None,
    ) -> None:
        self._workspace = Path(workspace).resolve(strict=True)
        self._config = config or ActionBenchmarkConfig()
        self._process = process or psutil.Process()

    def run(self, history_path: str | Path | None = None) -> ActionBenchmarkResult:
        """Run warm-ups and samples, comparing the median to rolling history."""

        registry = ExecutorRegistry()
        registry.register(
            "file",
            FileExecutor(
                self._workspace,
                verifier=FileVerifier(),
                capability_manager=CapabilityManager.allowing(Capability.FILE_WRITE),
            ),
        )
        for index in range(self._config.warmup_runs):
            self._invoke(registry, index, warmup=True)

        samples: list[float] = []
        successful_runs = 0
        false_success_count = 0
        peak_memory_mb = self._memory_mb()
        for index in range(self._config.sample_runs):
            started_ns = time.perf_counter_ns()
            result = self._invoke(registry, index, warmup=False)
            samples.append((time.perf_counter_ns() - started_ns) / 1_000_000)
            peak_memory_mb = max(peak_memory_mb, self._memory_mb())
            successful_runs += int(result.success)
            false_success_count += int(
                result.success and (not result.executed or not result.verified)
            )

        median_latency_ms = statistics.median(samples)
        platform_key = self._platform_key()
        baseline = self._rolling_baseline(history_path, platform_key)
        regression_ratio = (
            None
            if baseline is None or baseline == 0
            else (median_latency_ms - baseline) / baseline
        )
        regression_passed = (
            regression_ratio is None
            or regression_ratio <= self._config.regression_tolerance
        )
        memory_passed = peak_memory_mb < self._config.memory_ceiling_mb
        passed = (
            successful_runs == self._config.sample_runs
            and false_success_count == 0
            and regression_passed
            and memory_passed
        )
        return ActionBenchmarkResult(
            samples_ms=tuple(samples),
            median_latency_ms=median_latency_ms,
            baseline_median_ms=baseline,
            regression_ratio=regression_ratio,
            regression_tolerance=self._config.regression_tolerance,
            regression_passed=regression_passed,
            successful_runs=successful_runs,
            false_success_count=false_success_count,
            peak_memory_mb=peak_memory_mb,
            memory_ceiling_mb=self._config.memory_ceiling_mb,
            memory_passed=memory_passed,
            passed=passed,
            platform_key=platform_key,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def record(
        self,
        result: ActionBenchmarkResult,
        history_path: str | Path,
    ) -> None:
        """Append a passing measurement to bounded platform-specific history."""

        if not result.passed:
            raise ValueError("failing benchmark results cannot become a baseline")
        path = Path(history_path)
        history = self._load_history(path)
        history.append(
            {
                "platform_key": result.platform_key,
                "median_latency_ms": result.median_latency_ms,
                "peak_memory_mb": result.peak_memory_mb,
                "timestamp": result.timestamp,
            }
        )
        max_entries = self._config.rolling_window * 4
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(history[-max_entries:], indent=2) + "\n",
            encoding="utf-8",
        )

    def _invoke(
        self,
        registry: ExecutorRegistry,
        index: int,
        *,
        warmup: bool,
    ) -> Any:
        prefix = "warmup" if warmup else "sample"
        action = Action(
            executor="file",
            operation="write",
            parameters={
                "path": f"action-benchmark-{prefix}.txt",
                "content": f"Kattappa benchmark payload {index}",
            },
        )
        return registry.resolve(action.executor).execute(action)

    def _rolling_baseline(
        self,
        history_path: str | Path | None,
        platform_key: str,
    ) -> float | None:
        if history_path is None:
            return None
        matching = [
            float(entry["median_latency_ms"])
            for entry in self._load_history(Path(history_path))
            if entry.get("platform_key") == platform_key
            and isinstance(entry.get("median_latency_ms"), (int, float))
        ]
        if not matching:
            return None
        return statistics.median(matching[-self._config.rolling_window :])

    @staticmethod
    def _load_history(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid benchmark history: {path}") from exc
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise ValueError(f"benchmark history must be a JSON list: {path}")
        return value

    def _memory_mb(self) -> float:
        return self._process.memory_info().rss / (1024 * 1024)

    @staticmethod
    def _platform_key() -> str:
        return "-".join(
            (
                platform.system().casefold(),
                platform.machine().casefold(),
                platform.python_version(),
            )
        )
