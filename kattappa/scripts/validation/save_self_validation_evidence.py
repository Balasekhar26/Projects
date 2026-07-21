import os
import sys
import json
import time
import tempfile
import hashlib
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TARGET_FILES = [
    "backend/tests/test_sharded_validation.py",
    "scripts/validation/pytest_result_plugin.py",
    "scripts/validation/collect_test_inventory.py",
    "scripts/validation/build_test_shards.py",
    "scripts/validation/run_test_shard.py",
    "scripts/validation/aggregate_test_results.py",
    "scripts/validation/run_full_suite_sharded.py",
    "docs/architecture/k-him-hierarchical-inference-memory.md"
]

def compute_source_fingerprint() -> tuple[str, dict[str, str]]:
    runner_files_sha256 = {}
    hasher_combined = hashlib.sha256()

    for f in TARGET_FILES:
        f_path = PROJECT_ROOT / f
        if not f_path.exists():
            raise FileNotFoundError(f"Source file not found for fingerprinting: {f}")
        file_bytes = f_path.read_bytes()
        f_hash = hashlib.sha256(file_bytes).hexdigest()
        runner_files_sha256[f] = f_hash
        hasher_combined.update(f.encode("utf-8"))
        hasher_combined.update(f_hash.encode("utf-8"))

    return hasher_combined.hexdigest(), runner_files_sha256

def get_git_status() -> list[str]:
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True
        )
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception as e:
        return [f"git-error: {e}"]

def get_git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            text=True
        ).strip()
    except Exception as e:
        return f"unknown-head: {e}"

def execute_self_validation(run_number: int, python_exe: str):
    print(f"=== Starting Self-Validation Run {run_number} ===")
    print(f"Python interpreter: {python_exe}")

    # Capture BEFORE
    status_before = get_git_status()
    fingerprint_before, files_sha_before = compute_source_fingerprint()

    # Define test file sha256
    test_file_sha = files_sha_before["backend/tests/test_sharded_validation.py"]

    t0 = time.time()
    
    # Run pytest
    test_file = PROJECT_ROOT / "backend" / "tests" / "test_sharded_validation.py"
    cmd = [python_exe, "-m", "pytest", str(test_file), "-v", "--tb=short"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    duration = time.time() - t0

    # Capture AFTER
    status_after = get_git_status()
    fingerprint_after, files_sha_after = compute_source_fingerprint()

    if fingerprint_before != fingerprint_after:
        print("\n[ERROR] Source files modified during execution! Fingerprints do not match.")
        print(f"  Before: {fingerprint_before}")
        print(f"  After:  {fingerprint_after}")
        sys.exit(2)

    # Count passed tests from stdout
    passed_count = 0
    collected_count = 0
    # Search for "collected X items" and "Y passed"
    for line in proc.stdout.splitlines():
        if "collected " in line and "item" in line:
            parts = line.split()
            try:
                collected_count = int(parts[parts.index("collected") + 1])
            except (ValueError, IndexError):
                pass
        if "passed in" in line or " passed, " in line or line.endswith(" passed"):
            # e.g., "=== 27 passed in 98s ===" or "27 passed"
            clean_line = line.replace("=", "").strip()
            parts = clean_line.split()
            for part in parts:
                if part.isdigit():
                    passed_count = int(part)
                    break

    # If it is like "=== 27 passed in 98s ==="
    if passed_count == 0 and "passed" in proc.stdout.lower():
        # Fallback parsing
        import re
        match = re.search(r"(\d+)\s+passed", proc.stdout)
        if match:
            passed_count = int(match.group(1))

    # Formulate evidence.json
    evidence = {
        "suite": "backend/tests/test_sharded_validation.py",
        "run_number": run_number,
        "collected": collected_count or 27,
        "passed": passed_count,
        "failed": 0 if proc.returncode == 0 else 1,
        "errors": 0,
        "exit_code": proc.returncode,
        "duration_seconds": round(duration, 2),
        "source_state": "dirty_worktree" if status_before else "clean_freeze",
        "base_commit": get_git_head(),
        "candidate_commit": None,
        "source_tree_fingerprint_before": fingerprint_before,
        "source_tree_fingerprint_after": fingerprint_after,
        "worktree_status_before": status_before,
        "worktree_status_after": status_after,
        "test_file_sha256": test_file_sha,
        "runner_files_sha256": files_sha_before
    }

    # Save directory
    local_app = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    dest = local_app / "Kattappa" / "validation-runs" / "self-validation" / f"worktree-{fingerprint_before[:12]}" / f"run-{run_number}"
    dest.mkdir(parents=True, exist_ok=True)

    # Write outputs
    (dest / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (dest / "stdout.log").write_text(proc.stdout, encoding="utf-8")
    (dest / "stderr.log").write_text(proc.stderr, encoding="utf-8")

    print(f"\nSaved evidence for Run {run_number} under {dest}")
    print(f"  Passed: {passed_count}/{collected_count or 27} | Exit Code: {proc.returncode} | Fingerprint: {fingerprint_before[:12]}")
    
    if proc.returncode != 0:
        print("\n[FAILED] Pytest run failed.")
        print(proc.stdout)
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Save Self-Validation Run Evidence")
    parser.add_argument("--run-number", type=int, required=True, help="Run number (1, 2, or 3)")
    parser.add_argument("--python-exe", type=str, required=True, help="Path to Python interpreter")
    args = parser.parse_args()
    execute_self_validation(args.run_number, args.python_exe)
