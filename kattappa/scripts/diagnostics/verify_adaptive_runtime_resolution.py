"""Prove adaptive-runtime source resolution and pytest determinism."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ADAPTIVE_SOURCE = ROOT / "backend" / "core" / "adaptive_runtime.py"
ADAPTIVE_TEST = ROOT / "backend" / "tests" / "test_adaptive_runtime.py"
DEFAULT_OUTPUT = ROOT / "artifacts" / "diagnostics" / "adaptive-runtime-resolution.json"

CANONICAL_FIXTURES: dict[str, dict[str, Any]] = {
    "ECO_LOW_RAM": {
        "ram_total_gb": 4.0,
        "has_gpu_acceleration": True,
        "on_ac_power": True,
        "gpu_vram_gb": 2.0,
    },
    "ECO_BATTERY_CPU": {
        "ram_total_gb": 16.0,
        "has_gpu_acceleration": False,
        "on_ac_power": False,
        "gpu_vram_gb": 0.0,
    },
    "BALANCED_AC_GPU": {
        "ram_total_gb": 12.0,
        "has_gpu_acceleration": True,
        "on_ac_power": True,
        "gpu_vram_gb": 4.0,
    },
}


def sha256(path: Path) -> str:
    """Return a deterministic source digest."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_cache_paths() -> list[Path]:
    """Return only disposable caches owned by this checkout."""

    caches = list((ROOT / "backend").rglob("__pycache__"))
    caches.extend(path for path in (ROOT / ".pytest_cache",) if path.exists())
    return caches


def clear_project_caches() -> None:
    """Remove project-local caches without touching the virtual environment."""

    root = ROOT.resolve()
    venv = (ROOT / "ai_system_env").resolve()
    for cache in project_cache_paths():
        resolved = cache.resolve()
        if root not in resolved.parents or resolved == root or venv in resolved.parents:
            raise RuntimeError(f"refusing to remove unsafe cache path: {resolved}")
        shutil.rmtree(resolved)


def snapshot() -> dict[str, Any]:
    """Capture the exact package, module, source, and profile implementation."""

    import backend
    import backend.core.adaptive_runtime as adaptive_runtime
    from backend.core.adaptive_runtime import PerformanceProfile

    module_path = Path(adaptive_runtime.__file__).resolve()
    return {
        "backend_package_path": str(Path(backend.__file__).resolve()),
        "adaptive_runtime_module_path": str(module_path),
        "adaptive_runtime_source_sha256": sha256(module_path),
        "adaptive_runtime_compiled_path": getattr(adaptive_runtime, "__cached__", None),
        "resolve_profile_source": inspect.getsource(PerformanceProfile.resolve_profile),
        "sys_path": sys.path,
        "kattappa_test_mode": os.getenv("KATTAPPA_TEST_MODE"),
        "profile_results": {
            name: PerformanceProfile.resolve_profile(dict(fixture))
            for name, fixture in CANONICAL_FIXTURES.items()
        },
    }


def run_child(
    arguments: list[str], *, timeout: float = 300.0
) -> subprocess.CompletedProcess[str]:
    """Run one isolated Python process with deterministic checkout context."""

    environment = os.environ.copy()
    environment["KATTAPPA_TEST_MODE"] = "true"
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class AdaptiveRunCollector:
    """Capture inventory before `-k` deselection and the selected test result."""

    def __init__(self) -> None:
        self.node_ids: list[str] = []
        self.profile_outcome: str | None = None

    @staticmethod
    def pytest_collection_modifyitems(items: list[Any]) -> None:
        # Replaced per instance below so pytest receives a bound hook.
        del items

    def pytest_runtest_logreport(self, report: Any) -> None:
        if "performance_profile" in report.nodeid and report.when == "call":
            self.profile_outcome = report.outcome


def single_run() -> dict[str, Any]:
    """Collect and execute the profile test in one fresh Python process."""

    import pytest

    collector = AdaptiveRunCollector()

    @pytest.hookimpl(tryfirst=True)
    def capture_inventory(items: list[Any]) -> None:
        collector.node_ids = sorted(item.nodeid for item in items)

    collector.pytest_collection_modifyitems = capture_inventory  # type: ignore[method-assign]
    output = StringIO()
    errors = StringIO()
    with redirect_stdout(output), redirect_stderr(errors):
        returncode = int(
            pytest.main(
                [
                    "backend/tests/test_adaptive_runtime.py",
                    "-q",
                    "-k",
                    "performance_profile",
                ],
                plugins=[collector],
            )
        )
    return {
        "snapshot": snapshot(),
        "collection": {
            "returncode": returncode,
            "count": len(collector.node_ids),
            "node_ids": collector.node_ids,
            "stdout": output.getvalue(),
            "stderr": errors.getvalue(),
        },
        "performance_profile_test": {
            "returncode": returncode,
            "passed": collector.profile_outcome == "passed" and returncode == 0,
            "outcome": collector.profile_outcome,
        },
        "source_hashes": {
            "adaptive_runtime": sha256(ADAPTIVE_SOURCE),
            "adaptive_runtime_test": sha256(ADAPTIVE_TEST),
        },
    }


def run_repetitions(count: int, output: Path, *, resume: bool) -> int:
    """Run collection and the profile test repeatedly in clean subprocesses."""

    partial = output.resolve().with_suffix(output.suffix + ".partial")
    runs: list[dict[str, Any]] = []
    if resume and partial.exists():
        runs = json.loads(partial.read_text(encoding="utf-8"))["runs"]
        current_hashes = {
            "adaptive_runtime": sha256(ADAPTIVE_SOURCE),
            "adaptive_runtime_test": sha256(ADAPTIVE_TEST),
        }
        if any(run["source_hashes"] != current_hashes for run in runs):
            raise RuntimeError("partial evidence belongs to a different source state")
        if len(runs) > count:
            raise RuntimeError("partial evidence contains more runs than requested")

    for index in range(len(runs), count):
        clear_project_caches()
        child = run_child([str(Path(__file__).resolve()), "--single-run"])
        if child.returncode != 0:
            raise RuntimeError(child.stderr or child.stdout)
        run = json.loads(child.stdout)
        run["run"] = index + 1
        runs.append(run)

        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text(
            json.dumps({"runs": runs}, indent=2) + "\n", encoding="utf-8"
        )

    signatures = {
        json.dumps(
            {
                "module": run["snapshot"]["adaptive_runtime_module_path"],
                "module_hash": run["snapshot"]["adaptive_runtime_source_sha256"],
                "source_hashes": run["source_hashes"],
                "node_ids": run["collection"]["node_ids"],
                "profile_results": run["snapshot"]["profile_results"],
                "test_passed": run["performance_profile_test"]["passed"],
            },
            sort_keys=True,
        )
        for run in runs
    }
    stable = len(signatures) == 1 and all(
        run["collection"]["returncode"] == 0
        and run["performance_profile_test"]["passed"]
        for run in runs
    )
    report = {
        "stable": stable,
        "repetitions": count,
        "unique_signatures": len(signatures),
        "runs": runs,
    }
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    output.with_suffix(output.suffix + ".partial").unlink(missing_ok=True)
    print(json.dumps({"stable": stable, "runs": count, "output": str(output)}))
    return 0 if stable else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--snapshot", action="store_true")
    result.add_argument("--single-run", action="store_true")
    result.add_argument("--repeat", type=int, default=10)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--resume", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.snapshot:
        print(json.dumps(snapshot(), indent=2))
        return 0
    if args.single_run:
        print(json.dumps(single_run()))
        return 0
    if args.repeat < 1:
        raise ValueError("--repeat must be positive")
    return run_repetitions(args.repeat, args.output, resume=args.resume)


if __name__ == "__main__":
    raise SystemExit(main())
