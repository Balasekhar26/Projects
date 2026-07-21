import sys
import os
import json
import time
import subprocess
from pathlib import Path

ROOT = Path(r"C:\Users\balu\Projects\kattappa").resolve()
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

from collect_test_inventory import collect_inventory
from build_test_shards import build_manifest
from run_test_shard import run_shard
from aggregate_test_results import aggregate_results

def verify_source_provenance() -> tuple[bool, str, str]:
    try:
        head_sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        status = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain", "-uno"], text=True).strip()
        
        # Verify runner files are tracked
        runner_files = [
            "scripts/validation/collect_test_inventory.py",
            "scripts/validation/build_test_shards.py",
            "scripts/validation/run_test_shard.py",
            "scripts/validation/aggregate_test_results.py",
            "scripts/validation/run_full_suite_sharded.py",
            "scripts/validation/test_shard_policy.yaml"
        ]
        for f in runner_files:
            try:
                subprocess.check_output(["git", "-C", str(ROOT), "cat-file", "-e", f"HEAD:{f}"], stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError:
                return False, head_sha, f"Runner file '{f}' is not tracked in HEAD {head_sha[:8]}"

        if status:
            return False, head_sha, f"Dirty working tree detected: {status}"

        return True, head_sha, "Source provenance verified"
    except Exception as e:
        return False, "unknown", str(e)

def run_full_sharded_suite(shard_size: int = 250):
    evidence_dir = ROOT / "docs" / "evidence" / "k-r0.5"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    print("--- 0. Verifying Source Provenance & Worktree ---")
    valid_start, start_sha, msg = verify_source_provenance()
    print(f"Commit SHA: {start_sha[:12]} | Provenance: {msg}")
    if not valid_start:
        print(f"WARNING: Worktree is uncommitted or untracked scripts exist. Run will be marked INVALID for release.")

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

    print("\n--- 4. Verifying Post-Execution Worktree Integrity ---")
    valid_end, end_sha, end_msg = verify_source_provenance()
    if start_sha != end_sha or not valid_end:
        print(f"CRITICAL: Worktree status changed during execution. Invalidation flag set.")

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
