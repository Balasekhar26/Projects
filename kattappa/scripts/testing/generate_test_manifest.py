"""Generate reproducible pytest collection evidence in a fresh subprocess."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTION = (
    "backend/tests",
    "kattappa_native/tests",
    "kattappa_data_engine/tests",
    "kattappa_runtime/resource_governor",
)


def command_output(arguments: list[str]) -> str:
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def git_state() -> dict[str, Any]:
    status = command_output(["git", "status", "--short"])
    return {
        "commit": command_output(["git", "rev-parse", "HEAD"]),
        "dirty": bool(status),
        "status": status.splitlines(),
    }


def pytest_version() -> str:
    output = command_output([sys.executable, "-m", "pytest", "--version"])
    return output.split()[1]


def collect(selection: list[str]) -> tuple[list[str], dict[str, Any]]:
    environment = os.environ.copy()
    environment["KATTAPPA_TEST_MODE"] = "true"
    with tempfile.TemporaryDirectory(prefix="kattappa-manifest-") as directory:
        node_path = Path(directory) / "nodeids.txt"
        audit_path = Path(directory) / "markers.json"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "collect_pytest_nodeids.py"),
                *selection,
                "--output",
                str(node_path),
                "--audit-output",
                str(audit_path),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)
        node_ids = sorted(node_path.read_text(encoding="utf-8").splitlines())
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    return node_ids, audit


class ExecutionCollector:
    """Capture the inventory and terminal outcomes from one pytest process."""

    def __init__(self, output: Path) -> None:
        self.output = output
        self.started = time.perf_counter()
        self.node_ids: list[str] = []
        self.markers: dict[str, set[str]] = {}
        self.config: Any = None

    def pytest_configure(self, config: Any) -> None:
        self.config = config

    def pytest_collection_finish(self, session: Any) -> None:
        self.node_ids = sorted(item.nodeid for item in session.items)
        self.markers = {
            item.nodeid: {marker.name for marker in item.iter_markers()}
            for item in session.items
        }

    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        reporter = self.config.pluginmanager.get_plugin("terminalreporter")
        stats = reporter.stats if reporter is not None else {}
        outcomes = {
            name: len(stats.get(name, []))
            for name in ("passed", "failed", "skipped", "xfailed", "xpassed", "error")
        }
        payload = {
            "exit_code": int(exitstatus),
            "duration_seconds": time.perf_counter() - self.started,
            "warnings": len(stats.get("warnings", [])),
            "outcomes": outcomes,
            "node_ids": self.node_ids,
            "markers": marker_counts(self.markers),
        }
        self.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def marker_counts(markers_by_node: dict[str, set[str]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    tracked = {"unit", "integration", "evaluation", "safety"}
    for markers in markers_by_node.values():
        counts.update(markers & tracked)
    return {name: counts.get(name, 0) for name in sorted(tracked)}


def execute_child(selection: list[str], output: Path) -> int:
    import pytest

    collector = ExecutionCollector(output)
    return int(pytest.main(selection, plugins=[collector]))


def execute(selection: list[str]) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["KATTAPPA_TEST_MODE"] = "true"
    with tempfile.TemporaryDirectory(prefix="kattappa-execution-") as directory:
        output = Path(directory) / "execution.json"
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--execute-child",
                str(output),
                *selection,
            ],
            cwd=ROOT,
            env=environment,
            timeout=3600,
            check=False,
        )
        if not output.exists():
            raise RuntimeError("pytest execution did not produce a result manifest")
        payload = json.loads(output.read_text(encoding="utf-8"))
        payload["process_returncode"] = result.returncode
        return payload


def build_manifest(selection: list[str], *, run_tests: bool) -> dict[str, Any]:
    node_ids, audit = collect(selection)
    primary = audit["primary_counts"]
    secondary = audit["secondary_counts"]
    manifest = {
        "git": git_state(),
        "environment": {
            "python": platform.python_version(),
            "pytest": pytest_version(),
            "platform": sys.platform,
        },
        "selection": selection,
        "collection": {
            "total": len(node_ids),
            "node_ids": node_ids,
            "markers": {
                "unit": primary.get("unit", 0),
                "integration": primary.get("integration", 0),
                "evaluation": primary.get("evaluation", 0),
                "safety": secondary.get("safety", 0),
            },
            "marker_audit": audit,
        },
    }
    if run_tests:
        execution = execute(selection)
        execution["collection_matches_manifest"] = execution["node_ids"] == node_ids
        manifest["execution"] = execution
    return manifest


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("selection", nargs="*", default=list(DEFAULT_SELECTION))
    result.add_argument("--output", type=Path)
    result.add_argument("--run", action="store_true")
    result.add_argument("--execute-child", type=Path, help=argparse.SUPPRESS)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.execute_child is not None:
        return execute_child(list(args.selection), args.execute_child)
    manifest = build_manifest(list(args.selection), run_tests=args.run)
    output = args.output
    if output is None:
        output = (
            ROOT / "artifacts" / "test-manifests" / f"{manifest['git']['commit']}.json"
        )
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"total": manifest["collection"]["total"], "output": str(output)}))
    if args.run and manifest["execution"]["exit_code"] != 0:
        return int(manifest["execution"]["exit_code"])
    if args.run and not manifest["execution"]["collection_matches_manifest"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
