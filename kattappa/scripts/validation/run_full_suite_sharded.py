import sys
import os
import json
import time
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "validation"))

from collect_test_inventory import collect_inventory
from build_test_shards import build_manifest
from run_test_shard import run_shard
from aggregate_test_results import aggregate_results

def verify_source_provenance() -> tuple[bool, str, list[str]]:
    errors = []
    try:
        head_sha = subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"], text=True).strip()
        
        # 1. Verify all runner files are tracked in HEAD via git ls-tree
        runner_files = [
            "scripts/validation/collect_test_inventory.py",
            "scripts/validation/build_test_shards.py",
            "scripts/validation/run_test_shard.py",
            "scripts/validation/aggregate_test_results.py",
            "scripts/validation/run_full_suite_sharded.py",
            "scripts/validation/test_shard_policy.yaml"
        ]
        
        tracked_in_head = set(
            subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "ls-tree", "-r", "--name-only", "HEAD"], text=True).splitlines()
        )
        for f in runner_files:
            if f not in tracked_in_head:
                errors.append(f"Runner file '{f}' is not tracked in HEAD {head_sha[:8]}")

        # 2. Check worktree dirty status including untracked source files (--untracked-files=all)
        status_lines = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
            text=True
        ).splitlines()

        for line in status_lines:
            line_clean = line.strip()
            # Ignore runtime evidence artifacts directory
            if "docs/evidence/k-r0.5/" in line_clean or "evaluation/reflections/" in line_clean:
                continue
            if line_clean:
                errors.append(f"Dirty or untracked file in worktree: {line_clean}")

        return (len(errors) == 0), head_sha, errors
    except Exception as e:
        return False, "unknown", [f"Git provenance command failed: {e}"]

def run_full_sharded_suite(shard_size: int = 250):
    evidence_dir = PROJECT_ROOT / "docs" / "evidence" / "k-r0.5"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    print("--- 0. Fail-Closed Source Provenance & Worktree Preflight ---")
    valid_start, start_sha, errors = verify_source_provenance()
    print(f"Commit SHA: {start_sha[:12]}")
    
    if not valid_start:
        print("\n[FAILED] PROVENANCE PREFLIGHT FAILED. ABORTING RELEASE RUN.")
        for err in errors:
            print(f"  - {err}")
            
        verdict_payload = {
            "verdict": "INVALID",
            "valid_for_release": False,
            "commit_sha": start_sha,
            "reason": "SOURCE_PROVENANCE_FAILED",
            "errors": errors
        }
        with open(evidence_dir / "release-verdict.json", "w", encoding="utf-8") as f:
            json.dump(verdict_payload, f, indent=2)
        return 3

    print("[PASSED] Provenance Preflight Passed: All runner files tracked in HEAD, 0 untracked source files.")

    print("\n--- 1. Collecting Test Inventory ---")
    n_collected, c_hash, p_hash = collect_inventory(evidence_dir)

    print("\n--- 2. Building Shard Manifest ---")
    n_shards, m_hash = build_manifest(evidence_dir, shard_size=shard_size)

    print("\n--- 3. Executing Shards ---")
    manifest = json.loads((evidence_dir / "manifest.json").read_text(encoding="utf-8"))
    
    t0 = time.time()
    for s in manifest["shards"]:
        run_shard(s, evidence_dir)
    total_time = time.time() - t0

    print(f"\nCompleted all {n_shards} shards in {total_time:.2f}s")

    print("\n--- 4. Post-Execution Worktree Integrity Check ---")
    valid_end, end_sha, post_errors = verify_source_provenance()
    if start_sha != end_sha or not valid_end:
        print("\n[FAILED] POST-EXECUTION WORKTREE INTEGRITY FAILED.")
        for err in post_errors:
            print(f"  - {err}")

    print("\n--- 5. Aggregating Results & Generating Release Verdict ---")
    verdict = aggregate_results(evidence_dir)
    verdict["commit_sha"] = start_sha
    verdict["valid_for_release"] = (valid_start and valid_end and start_sha == end_sha and verdict["verdict"] == "PASS")
    
    if not verdict["valid_for_release"]:
        verdict["verdict"] = "INVALID"

    with open(evidence_dir / "release-verdict.json", "w", encoding="utf-8") as f:
        json.dump(verdict, f, indent=2)

    if verdict["valid_for_release"]:
        return 0
    else:
        return 1

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Kattappa K-R0.5 Sharded Full Suite Runner")
    parser.add_argument("--target-tests-per-shard", type=int, default=250, help="Target number of test nodes per shard")
    args = parser.parse_args()
    sys.exit(run_full_sharded_suite(shard_size=args.target_tests_per_shard))
