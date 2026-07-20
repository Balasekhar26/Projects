"""Tests for the compact Execution Stabilization health report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.ci_health_report import build_health_report, render_markdown
from scripts.collect_pytest_nodeids import build_classification_audit

pytestmark = pytest.mark.unit


def test_health_report_combines_all_acceptance_evidence(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuite tests="2" failures="0" errors="0" skipped="0">'
        '<testcase classname="backend.tests.test_action_runtime" name="test_unit" />'
        '<testcase classname="backend.tests.test_action_integration" name="test_e2e" />'
        "</testsuite>",
        encoding="utf-8",
    )
    mutation = tmp_path / "mutation.json"
    mutation.write_text(
        json.dumps(
            {"killed": 96, "survived": 4, "timeout": 0, "suspicious": 0, "segfault": 0}
        ),
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(
        json.dumps(
            {
                "regression_passed": True,
                "memory_passed": True,
                "false_success_count": 0,
                "peak_memory_mb": 128.0,
                "regression_ratio": 0.03,
            }
        ),
        encoding="utf-8",
    )
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        json.dumps(
            {
                "files": {
                    "backend/core/action/file_executor.py": {
                        "summary": {"covered_lines": 97, "num_statements": 100}
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    report = build_health_report(junit, mutation, benchmark, coverage)

    assert report["passed"] is True
    assert report["mutation"]["score"] == 0.96
    assert report["coverage"]["score"] == 0.97
    assert "Overall: **PASS**" in render_markdown(report)


def test_marker_audit_detects_missing_and_multiple_primary_classes() -> None:
    audit = build_classification_audit(
        {
            "test_ok": frozenset({"unit", "safety"}),
            "test_missing": frozenset({"performance"}),
            "test_multiple": frozenset({"unit", "integration"}),
        }
    )

    assert audit["primary_counts"] == {"integration": 1, "unit": 2}
    assert audit["secondary_counts"] == {"performance": 1, "safety": 1}
    assert audit["missing_primary_node_ids"] == ["test_missing"]
    assert audit["multiple_primary_node_ids"] == {
        "test_multiple": ["integration", "unit"]
    }
