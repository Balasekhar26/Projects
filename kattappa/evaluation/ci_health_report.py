"""Generate the compact Execution Stabilization CI health report."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class HealthThresholds:
    """Acceptance thresholds for execution stabilization."""

    mutation_score: float = 0.85
    safety_mutation_score: float = 0.95
    action_coverage: float = 0.95


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read CI artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"CI artifact must contain a JSON object: {path}")
    return value


def _test_summary(path: Path) -> dict[str, Any]:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError(f"unable to read JUnit report: {path}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    tests = sum(int(suite.attrib.get("tests", 0)) for suite in suites)
    failures = sum(int(suite.attrib.get("failures", 0)) for suite in suites)
    errors = sum(int(suite.attrib.get("errors", 0)) for suite in suites)
    skipped = sum(int(suite.attrib.get("skipped", 0)) for suite in suites)
    integration = sum(
        1
        for case in root.iter("testcase")
        if "action_integration" in case.attrib.get("classname", "")
    )
    return {
        "tests": tests,
        "passed": tests - failures - errors - skipped,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "integration_tests": integration,
        "passed_gate": tests > 0 and failures == 0 and errors == 0 and skipped == 0,
    }


def _mutation_summary(
    path: Path,
    thresholds: HealthThresholds,
) -> dict[str, Any]:
    data = _read_json(path)
    killed = int(data.get("killed", 0))
    survived = int(data.get("survived", 0))
    timeout = int(data.get("timeout", 0))
    suspicious = int(data.get("suspicious", 0))
    segfault = int(data.get("segfault", 0))
    scored = killed + survived + timeout + suspicious + segfault
    score = killed / scored if scored else 0.0
    return {
        "killed": killed,
        "survived": survived,
        "scored": scored,
        "score": score,
        "threshold": thresholds.mutation_score,
        "safety_threshold": thresholds.safety_mutation_score,
        "passed_gate": score >= thresholds.mutation_score,
        "passed_safety_gate": score >= thresholds.safety_mutation_score,
    }


def _coverage_summary(path: Path, threshold: float) -> dict[str, Any]:
    data = _read_json(path)
    files = data.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("coverage artifact has no files mapping")
    action_files = [
        value
        for name, value in files.items()
        if name.replace("\\", "/").startswith("backend/core/action/")
        and isinstance(value, dict)
    ]
    covered = sum(
        int(file_data.get("summary", {}).get("covered_lines", 0))
        for file_data in action_files
    )
    statements = sum(
        int(file_data.get("summary", {}).get("num_statements", 0))
        for file_data in action_files
    )
    percent = covered / statements if statements else 0.0
    return {
        "covered_lines": covered,
        "statements": statements,
        "score": percent,
        "threshold": threshold,
        "passed_gate": statements > 0 and percent >= threshold,
    }


def build_health_report(
    junit_path: Path,
    mutation_path: Path,
    benchmark_path: Path,
    coverage_path: Path,
    thresholds: HealthThresholds | None = None,
) -> dict[str, Any]:
    """Combine test, mutation, benchmark, memory, and coverage evidence."""

    active_thresholds = thresholds or HealthThresholds()
    tests = _test_summary(junit_path)
    mutation = _mutation_summary(mutation_path, active_thresholds)
    benchmark = _read_json(benchmark_path)
    coverage = _coverage_summary(coverage_path, active_thresholds.action_coverage)
    gates = {
        "tests": bool(tests["passed_gate"]),
        "integration": int(tests["integration_tests"]) > 0,
        "mutation": bool(mutation["passed_gate"]),
        "safety_mutation": bool(mutation["passed_safety_gate"]),
        "benchmark_regression": bool(benchmark.get("regression_passed", False)),
        "memory_ceiling": bool(benchmark.get("memory_passed", False)),
        "false_success": int(benchmark.get("false_success_count", -1)) == 0,
        "action_coverage": bool(coverage["passed_gate"]),
    }
    return {
        "passed": all(gates.values()),
        "gates": gates,
        "tests": tests,
        "mutation": mutation,
        "benchmark": benchmark,
        "coverage": coverage,
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact human-readable CI dashboard."""

    gates = report["gates"]
    tests = report["tests"]
    mutation = report["mutation"]
    benchmark = report["benchmark"]
    coverage = report["coverage"]

    def status(passed: bool) -> str:
        return "PASS" if passed else "FAIL"

    rows = [
        (
            "Unit and integration",
            status(gates["tests"] and gates["integration"]),
            f"{tests['passed']}/{tests['tests']}",
        ),
        ("Mutation score", status(gates["mutation"]), f"{mutation['score']:.1%}"),
        (
            "Safety mutation",
            status(gates["safety_mutation"]),
            f"{mutation['score']:.1%}",
        ),
        (
            "Benchmark regression",
            status(gates["benchmark_regression"]),
            _regression_text(benchmark),
        ),
        (
            "Memory ceiling",
            status(gates["memory_ceiling"]),
            f"{float(benchmark.get('peak_memory_mb', 0)):.1f} MB",
        ),
        (
            "False success",
            status(gates["false_success"]),
            str(benchmark.get("false_success_count", "unknown")),
        ),
        (
            "Action coverage",
            status(gates["action_coverage"]),
            f"{coverage['score']:.1%}",
        ),
    ]
    lines = [
        "# Execution Stabilization Health",
        "",
        "| Gate | Status | Evidence |",
        "| --- | --- | ---: |",
    ]
    lines.extend(
        f"| {name} | {gate_status} | {evidence} |"
        for name, gate_status, evidence in rows
    )
    lines.extend(("", f"Overall: **{status(bool(report['passed']))}**", ""))
    return "\n".join(lines)


def _regression_text(benchmark: dict[str, Any]) -> str:
    regression = benchmark.get("regression_ratio")
    return "baseline pending" if regression is None else f"{float(regression):+.1%}"


def build_parser() -> argparse.ArgumentParser:
    """Build the report command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--mutation", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    """Generate both machine-readable and Markdown health reports."""

    args = build_parser().parse_args()
    report = build_health_report(
        args.junit,
        args.mutation,
        args.benchmark,
        args.coverage,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    return 1 if args.strict and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
