#!/usr/bin/env python
"""Tool Coverage Probe — Kattappa M38.

Loads ``evaluation/tool_coverage_matrix.yaml`` and for each capability:

1. Detects backend availability via import probe (OPTIONAL_DEPENDENCY /
   HARDWARE_REQUIRED capabilities).
2. Sends the ``probe_prompt`` to the live Kattappa ``/chat`` API and checks
   that ``state.selected_agent`` matches ``expected_agent``.
3. Writes a structured ``evaluation/tool_coverage_report.json``.

Usage::

    # Full probe (requires live API on port 8000)
    python evaluation/run_tool_coverage.py

    # Dependency-probe only (no API calls)
    python evaluation/run_tool_coverage.py --deps-only

    # Show only failures and stubs
    python evaluation/run_tool_coverage.py --failures-only
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests
import yaml

BASE_DIR = Path(__file__).parent.parent
MATRIX_PATH = Path(__file__).parent / "tool_coverage_matrix.yaml"
REPORT_PATH = Path(__file__).parent / "tool_coverage_report.json"
API_URL = "http://localhost:8000/api/v1/chat"
API_TIMEOUT = 30

# Status constants
STATUS_PASS             = "PASS"
STATUS_FAIL             = "FAIL"
STATUS_STUB             = "STUB"
STATUS_DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
STATUS_AGENT_MISMATCH   = "AGENT_MISMATCH"
STATUS_API_ERROR        = "API_ERROR"
STATUS_SKIPPED          = "SKIPPED"


def _probe_dependency(module_name: str) -> bool:
    """Return True if the module can be imported."""
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


def _probe_routing(prompt: str, expected_agent: str) -> dict[str, Any]:
    """Send prompt to /chat and check selected_agent matches expected."""
    try:
        resp = requests.post(
            API_URL,
            json={"message": prompt},
            timeout=API_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        state = data.get("state", {})
        actual_agent = state.get("selected_agent", "")
        if actual_agent == expected_agent:
            return {"status": STATUS_PASS, "actual_agent": actual_agent}
        else:
            return {
                "status": STATUS_AGENT_MISMATCH,
                "expected_agent": expected_agent,
                "actual_agent": actual_agent,
                "result_preview": str(state.get("result", ""))[:120],
            }
    except requests.exceptions.ConnectionError:
        return {"status": STATUS_API_ERROR, "error": "API not reachable (is the server running?)"}
    except requests.exceptions.Timeout:
        return {"status": STATUS_API_ERROR, "error": f"Timeout after {API_TIMEOUT}s"}
    except Exception as exc:
        return {"status": STATUS_API_ERROR, "error": str(exc)}


def run_coverage(deps_only: bool = False) -> list[dict[str, Any]]:
    matrix = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))
    capabilities = matrix.get("capabilities", [])

    results: list[dict[str, Any]] = []

    for cap in capabilities:
        cap_id       = cap["id"]
        label        = cap.get("label", cap_id)
        backend_type = cap.get("backend_type", "STDLIB")
        backend_dep  = cap.get("backend_dep")
        probe_prompt = cap.get("probe_prompt", "")
        expected_agent = cap.get("expected_agent", "")

        row: dict[str, Any] = {
            "id": cap_id,
            "label": label,
            "backend_type": backend_type,
            "expected_agent": expected_agent,
        }

        # ── Stub: no probe needed ──────────────────────────────────────────
        if backend_type == "STUB":
            row["status"] = STATUS_STUB
            row["note"] = "No backend implemented — stub agent only."
            results.append(row)
            continue

        # ── Optional dependency: probe import ─────────────────────────────
        if backend_dep:
            available = _probe_dependency(backend_dep)
            if not available:
                row["status"] = STATUS_DEPENDENCY_MISSING
                row["note"] = f"Optional dependency '{backend_dep}' not installed."
                results.append(row)
                continue

        # ── Skip routing probe if deps_only mode ──────────────────────────
        if deps_only:
            row["status"] = STATUS_SKIPPED
            row["note"] = "--deps-only: routing probe skipped."
            results.append(row)
            continue

        # ── Routing probe via live API ─────────────────────────────────────
        probe_result = _probe_routing(probe_prompt, expected_agent)
        row.update(probe_result)
        results.append(row)

    return results


def _print_report(results: list[dict[str, Any]], failures_only: bool) -> None:
    counts = {s: 0 for s in [STATUS_PASS, STATUS_FAIL, STATUS_STUB, STATUS_DEPENDENCY_MISSING,
                               STATUS_AGENT_MISMATCH, STATUS_API_ERROR, STATUS_SKIPPED]}

    for r in results:
        s = r.get("status", "UNKNOWN")
        counts[s] = counts.get(s, 0) + 1

    print("\n" + "=" * 60)
    print("TOOL COVERAGE REPORT")
    print("=" * 60)

    for r in results:
        status = r.get("status", "UNKNOWN")
        if failures_only and status in (STATUS_PASS, STATUS_SKIPPED):
            continue
        icon = {
            STATUS_PASS:               "[PASS]",
            STATUS_STUB:               "[STUB]",
            STATUS_DEPENDENCY_MISSING: "[MISS]",
            STATUS_AGENT_MISMATCH:     "[MISMATCH]",
            STATUS_API_ERROR:          "[ERROR]",
            STATUS_FAIL:               "[FAIL]",
            STATUS_SKIPPED:            "[SKIP]",
        }.get(status, "[?]")
        print(f"\n  {icon} [{status:20s}] {r['label']} ({r['id']})")
        if "actual_agent" in r:
            print(f"             Expected: {r['expected_agent']}  →  Got: {r['actual_agent']}")
        if "note" in r:
            print(f"             {r['note']}")
        if "error" in r:
            print(f"             Error: {r['error']}")
        if "result_preview" in r:
            print(f"             Result preview: {r['result_preview']}")

    total = len(results)
    passed = counts[STATUS_PASS]
    stub_count = counts[STATUS_STUB]
    missing = counts[STATUS_DEPENDENCY_MISSING]

    print("\n" + "=" * 60)
    print("COVERAGE SUMMARY")
    print(f"  Total capabilities:    {total}")
    print(f"  PASS (routing OK):     {passed}")
    print(f"  STUB (no backend):     {stub_count}")
    print(f"  DEPENDENCY_MISSING:    {missing}")
    print(f"  AGENT_MISMATCH:        {counts[STATUS_AGENT_MISMATCH]}")
    print(f"  API_ERROR:             {counts[STATUS_API_ERROR]}")
    print(f"  Skipped:               {counts[STATUS_SKIPPED]}")
    if total > 0:
        effective = total - stub_count
        pct = (passed / effective * 100) if effective else 0
        print(f"\n  Effective pass rate (excl. stubs): {passed}/{effective} ({pct:.1f}%)")
    print("=" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kattappa Tool Coverage Probe")
    parser.add_argument("--deps-only", action="store_true",
                        help="Only probe dependencies, skip API routing checks.")
    parser.add_argument("--failures-only", action="store_true",
                        help="Only print failures, stubs, and missing dependencies.")
    args = parser.parse_args()

    print(f"\nLoading coverage matrix from: {MATRIX_PATH}")
    results = run_coverage(deps_only=args.deps_only)

    # Write report
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "capabilities": results,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved detailed report to: {REPORT_PATH}")

    _print_report(results, failures_only=args.failures_only)

    # Exit 1 if any non-stub failures
    hard_failures = [r for r in results
                     if r.get("status") in (STATUS_FAIL, STATUS_AGENT_MISMATCH, STATUS_API_ERROR)]
    if hard_failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
