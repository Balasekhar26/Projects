import sys
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

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

def audit_commit_scope(base_sha: str = "97d4bd9a5507479b5b5b903a9e09abf4bcc7b709", head_sha: str = "HEAD") -> int:
    try:
        resolved_head = subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "rev-parse", head_sha], text=True).strip()
        subject = subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "log", "-1", "--format=%s", resolved_head], text=True).strip()
        
        print(f"Auditing Range: {base_sha[:8]}..{resolved_head[:8]} ({subject})")
        
        errors = []

        # 1. Check all runner files exist in HEAD via git ls-tree
        tracked_in_head = set(
            subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "ls-tree", "-r", "--name-only", resolved_head], text=True).splitlines()
        )
        for rf in RUNNER_FILES:
            if rf not in tracked_in_head:
                errors.append(f"Validation runner file missing from {head_sha}: {rf}")

        # 2. Check worktree status for forbidden tracked data modifications
        status_lines = subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "status", "--porcelain"], text=True).splitlines()
        for line in status_lines:
            line_clean = line.strip()
            for f in FORBIDDEN_TRACKED_DATA:
                if f in line_clean:
                    errors.append(f"Tracked data file modified in worktree: {f}")

        # 3. Check diff in commit range for forbidden data files
        diff_files = subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "diff", "--name-only", f"{base_sha}..{resolved_head}"], text=True).splitlines()
        for f in diff_files:
            if f in FORBIDDEN_TRACKED_DATA:
                errors.append(f"Forbidden tracked data modification committed in range: {f}")

        if errors:
            print("\n[FAILED] COMMIT SCOPE VERIFICATION FAILED:")
            for err in errors:
                print(f"  - {err}")
            return 1

        print("\n[PASSED] COMMIT SCOPE VERIFICATION PASSED: All validation runner files tracked, 0 tracked data mutations.")
        return 0
    except Exception as e:
        print(f"\n[FAILED] Audit failed with error: {e}")
        return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit K-R0.5 commit scope and file tracking")
    parser.add_argument("--base", default="97d4bd9a5507479b5b5b903a9e09abf4bcc7b709", help="Base commit SHA")
    parser.add_argument("--head", default="HEAD", help="Head commit SHA")
    args = parser.parse_args()
    sys.exit(audit_commit_scope(args.base, args.head))
