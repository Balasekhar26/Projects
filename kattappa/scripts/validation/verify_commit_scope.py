import sys
import subprocess
from pathlib import Path

ROOT = Path(r"C:\Users\balu\Projects\kattappa").resolve()

RUNNER_FILES = [
    "scripts/validation/collect_test_inventory.py",
    "scripts/validation/build_test_shards.py",
    "scripts/validation/run_test_shard.py",
    "scripts/validation/aggregate_test_results.py",
    "scripts/validation/run_full_suite_sharded.py",
    "scripts/validation/test_shard_policy.yaml"
]

FORBIDDEN_TRACKED_DATA = [
    "backend/data/rbil_metrics.json",
    "backend/data/goals.json",
    "backend/data/world_model.json"
]

def audit_commit_scope():
    sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    subject = subprocess.check_output(["git", "-C", str(ROOT), "log", "-1", "--format=%s"], text=True).strip()
    
    print(f"Auditing Commit: {sha[:12]} - {subject}")
    
    errors = []
    
    # 1. Check all runner files exist in HEAD
    tracked_in_head = set(
        subprocess.check_output(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", "HEAD"], text=True).splitlines()
    )
    for rf in RUNNER_FILES:
        if rf not in tracked_in_head:
            errors.append(f"Validation runner file missing from HEAD: {rf}")

    # 2. Check worktree dirty files for tracked data modification
    status_lines = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).splitlines()
    for line in status_lines:
        line_clean = line.strip()
        for f in FORBIDDEN_TRACKED_DATA:
            if f in line_clean:
                errors.append(f"Tracked data file modified in worktree: {f}")

    if errors:
        print("\n[FAILED] COMMIT SCOPE VERIFICATION FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1
    
    print("\n[PASSED] COMMIT SCOPE VERIFICATION PASSED: All validation runner files tracked in HEAD, 0 tracked data mutations.")
    return 0

if __name__ == "__main__":
    sys.exit(audit_commit_scope())
