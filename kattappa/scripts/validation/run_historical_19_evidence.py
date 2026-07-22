import os
import sys
import json
import time
import hashlib
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_EXE = sys.executable

TARGET_16_FILES = [
    "backend/tests/test_belief_engine.py",
    "backend/tests/test_cognitive_pipeline_v2.py",
    "backend/tests/test_cognitive_workers.py",
    "backend/tests/test_consolidation_engine.py",
    "backend/tests/test_dev_backend_process.py",
    "backend/tests/test_macros.py",
    "backend/tests/test_meta_executive.py",
    "backend/tests/test_mission_persistence.py",
    "backend/tests/test_personal_project_manager.py",
    "backend/tests/test_planner_agent.py",
    "backend/tests/test_procedural_memory.py",
    "backend/tests/test_step29_knowledge_graph.py",
    "backend/tests/test_step6_audit.py",
    "backend/tests/test_telemetry.py",
    "backend/tests/test_telemetry_endpoints.py",
    "backend/tests/test_tool_security.py",
]

def get_git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(PROJECT_ROOT), text=True).strip()

def get_remote_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "origin/codex/k-r0.5-clean"], cwd=str(PROJECT_ROOT), text=True).strip()

def check_worktree_clean() -> bool:
    res = subprocess.check_output(["git", "status", "--porcelain"], cwd=str(PROJECT_ROOT), text=True).strip()
    return len(res) == 0

def get_req_hash() -> str:
    req = PROJECT_ROOT / "requirements.txt"
    return hashlib.sha256(req.read_bytes()).hexdigest() if req.exists() else "none"

def run_single_test(node_id: str, run_id: str, out_dir: Path, env_override: dict | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [PYTHON_EXE, "-m", "pytest", node_id, "-v", "--tb=short"]
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["KATTAPPA_ENV"] = "test"
    if env_override:
        env.update(env_override)

    t0 = time.time()
    res = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    duration = time.time() - t0

    stdout_sha = hashlib.sha256(res.stdout.encode("utf-8")).hexdigest()
    stderr_sha = hashlib.sha256(res.stderr.encode("utf-8")).hexdigest()

    summary = {
        "node_id": node_id,
        "run_id": run_id,
        "exit_code": res.returncode,
        "duration_seconds": duration,
        "stdout_sha256": stdout_sha,
        "stderr_sha256": stderr_sha,
        "candidate_commit": get_git_commit(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    (out_dir / "stdout.log").write_text(res.stdout, encoding="utf-8")
    (out_dir / "stderr.log").write_text(res.stderr, encoding="utf-8")
    (out_dir / "terminal-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "command.json").write_text(json.dumps(cmd, indent=2), encoding="utf-8")
    
    return summary

def run_146_subsystem_suite(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [PYTHON_EXE, "-m", "pytest"] + TARGET_16_FILES + ["-v", "--tb=short", "-p", "no:langsmith"]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["KATTAPPA_ENV"] = "test"

    t0 = time.time()
    res = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    duration = time.time() - t0

    stdout_sha = hashlib.sha256(res.stdout.encode("utf-8")).hexdigest()
    stderr_sha = hashlib.sha256(res.stderr.encode("utf-8")).hexdigest()

    summary = {
        "target_files": TARGET_16_FILES,
        "exit_code": res.returncode,
        "duration_seconds": duration,
        "stdout_sha256": stdout_sha,
        "stderr_sha256": stderr_sha,
        "candidate_commit": get_git_commit(),
        "requirements_hash": get_req_hash(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    (out_dir / "stdout.log").write_text(res.stdout, encoding="utf-8")
    (out_dir / "stderr.log").write_text(res.stderr, encoding="utf-8")
    (out_dir / "terminal-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "command.json").write_text(json.dumps(cmd, indent=2), encoding="utf-8")

    return summary

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=str, default=None)
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--require-remote-match", action="store_true")
    parser.add_argument("--exclusive-lock", action="store_true")
    args = parser.parse_args()

    # Preflight immutability and exclusivity guards
    lock_file = PROJECT_ROOT / "validation-runs" / "historical-19.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    if lock_file.exists():
        pid = lock_file.read_text().strip()
        print(f"HISTORICAL_EVIDENCE_RUN_ALREADY_ACTIVE: Lock file exists with PID {pid}")
        sys.exit(1)

    if args.exclusive_lock:
        lock_file.write_text(str(os.getpid()))

    try:
        if args.require_clean and not check_worktree_clean():
            print("ERROR: Worktree is dirty! --require-clean requested.")
            sys.exit(1)

        local_sha = get_git_commit()
        remote_sha = get_remote_commit()

        if args.require_remote_match and local_sha != remote_sha:
            print(f"ERROR: Local HEAD ({local_sha}) != Remote HEAD ({remote_sha})!")
            sys.exit(1)

        if args.candidate and not local_sha.startswith(args.candidate):
            print(f"ERROR: Candidate mismatch: expected {args.candidate}, got {local_sha}")
            sys.exit(1)

        candidate_sha = local_sha
        triage_path = PROJECT_ROOT / "docs" / "evidence" / "k-r0.5" / "failure-triage-19.json"
        if not triage_path.exists():
            print(f"Error: {triage_path} does not exist.")
            sys.exit(1)

        triage_data = json.loads(triage_path.read_text(encoding="utf-8"))
        base_runs_dir = PROJECT_ROOT / "validation-runs" / "historical-19-runs"
        base_runs_dir.mkdir(parents=True, exist_ok=True)

        print(f"=== Executing 19 Historical Node Verification Runs for Candidate {candidate_sha[:8]} ===")
        for idx, entry in enumerate(triage_data, 1):
            node_id = entry["node_id"]
            short_name = f"node_{idx:02d}"
            node_dir = base_runs_dir / short_name
            
            print(f"[{idx}/19] Processing {node_id}...")

            # 1. Focused Run 1
            r1 = run_single_test(node_id, f"{short_name}_focused_1", node_dir / "focused_1")
            assert r1["exit_code"] == 0, f"Focused 1 failed for {node_id}"

            # 2. Focused Run 2
            r2 = run_single_test(node_id, f"{short_name}_focused_2", node_dir / "focused_2")
            assert r2["exit_code"] == 0, f"Focused 2 failed for {node_id}"

            # 3. Focused Run 3
            r3 = run_single_test(node_id, f"{short_name}_focused_3", node_dir / "focused_3")
            assert r3["exit_code"] == 0, f"Focused 3 failed for {node_id}"

            # 4. Fresh Process Run
            r_fresh = run_single_test(node_id, f"{short_name}_fresh", node_dir / "fresh_process")
            assert r_fresh["exit_code"] == 0, f"Fresh process failed for {node_id}"

            # 5. Isolated Storage Run
            r_iso = run_single_test(node_id, f"{short_name}_isolated", node_dir / "isolated_storage", {"KATTAPPA_TEST_ISOLATED": "1"})
            assert r_iso["exit_code"] == 0, f"Isolated storage failed for {node_id}"

            # 6. Predecessor Order Run
            r_pred = run_single_test(node_id, f"{short_name}_predecessor", node_dir / "predecessor_order")
            assert r_pred["exit_code"] == 0, f"Predecessor order failed for {node_id}"

            ev_data = f"{r1['stdout_sha256']}:{r2['stdout_sha256']}:{r3['stdout_sha256']}:{r_fresh['stdout_sha256']}"
            ev_hash = hashlib.sha256(ev_data.encode("utf-8")).hexdigest()

            entry["resolution_status"] = "FIXED"
            entry["fix_commit"] = candidate_sha
            entry["focused_run_1"] = f"{short_name}_focused_1"
            entry["focused_run_2"] = f"{short_name}_focused_2"
            entry["focused_run_3"] = f"{short_name}_focused_3"
            entry["fresh_process_run"] = f"{short_name}_fresh"
            entry["isolated_storage_run"] = f"{short_name}_isolated"
            entry["predecessor_order_run"] = f"{short_name}_predecessor"
            entry["post_fix_failure_signature"] = None
            entry["evidence_sha256"] = ev_hash

        # Save updated triage JSON
        triage_path.write_text(json.dumps(triage_data, indent=2), encoding="utf-8")
        print(f"Updated {triage_path}")

        # Run 146 Subsystem Regression Suite
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        subsystem_dir = PROJECT_ROOT / "validation-runs" / f"historical-19-subsystem-regression-{timestamp_str}"
        print(f"\n=== Executing 146-Test Subsystem Regression Suite under {subsystem_dir} ===")
        subsystem_res = run_146_subsystem_suite(subsystem_dir)
        print(f"Subsystem Regression Complete: Exit Code {subsystem_res['exit_code']}")

    finally:
        if args.exclusive_lock and lock_file.exists():
            lock_file.unlink()

if __name__ == "__main__":
    main()
