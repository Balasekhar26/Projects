"""
Per-node diagnostic runner for Kattappa validation harness.
Collects harness nodes and executes each node in an isolated subprocess with a strict 180-second timeout.
Outputs machine-readable diagnostic JSON report.
"""

import sys
import os
import json
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def collect_harness_nodes():
    cmd = [
        sys.executable,
        "-m", "pytest",
        "backend/tests/test_sharded_validation.py",
        "--collect-only",
        "-q",
        "-o", "cache_dir=/dev/null",
        "-p", "no:langsmith"
    ]
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    nodes = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line and "::" in line:
            nodes.append(line)
    return nodes


def run_node_diagnosis(node_id, timeout_seconds=180):
    cmd = [
        sys.executable,
        "-m", "pytest",
        node_id,
        "-v",
        "-s",
        "-o", "cache_dir=/dev/null",
        "-p", "no:langsmith"
    ]
    
    t0 = time.time()
    status = "PASS"
    exit_code = -1
    stdout_str = ""
    stderr_str = ""

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        duration = time.time() - t0
        exit_code = proc.returncode
        stdout_str = proc.stdout or ""
        stderr_str = proc.stderr or ""
        if exit_code == 0:
            status = "PASS"
        else:
            status = "FAIL"
    except subprocess.TimeoutExpired as exc:
        duration = time.time() - t0
        status = "TIMEOUT"
        stdout_str = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
        stderr_str = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
    except Exception as exc:
        duration = time.time() - t0
        status = "ERROR"
        stderr_str = str(exc)

    return {
        "node_id": node_id,
        "status": status,
        "duration_seconds": round(duration, 3),
        "exit_code": exit_code,
        "stdout_tail": "\n".join(stdout_str.splitlines()[-20:]),
        "stderr_tail": "\n".join(stderr_str.splitlines()[-20:]),
        "child_pids": [],
        "cleanup_survivors": []
    }


def main():
    nodes = collect_harness_nodes()
    print(f"Collected {len(nodes)} harness nodes from backend/tests/test_sharded_validation.py")

    diag_dir = PROJECT_ROOT / "validation-runs" / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = diag_dir / f"harness-node-diagnosis-{timestamp}.json"

    results = []
    passed = 0
    failed = 0
    timed_out = 0

    for i, node in enumerate(nodes, 1):
        print(f"[{i}/{len(nodes)}] Running node: {node} ... ", end="", flush=True)
        res = run_node_diagnosis(node)
        results.append(res)
        print(f"{res['status']} in {res['duration_seconds']}s")
        if res["status"] == "PASS":
            passed += 1
        elif res["status"] == "TIMEOUT":
            timed_out += 1
        else:
            failed += 1

    summary = {
        "timestamp": timestamp,
        "total_nodes": len(nodes),
        "passed": passed,
        "failed": failed,
        "timed_out": timed_out,
        "results": results
    }

    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nDiagnosis complete. Report written to {report_path}")


if __name__ == "__main__":
    main()
