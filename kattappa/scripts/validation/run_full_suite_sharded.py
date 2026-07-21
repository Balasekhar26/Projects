import sys
import os
import json
import time
import uuid
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "validation"))

from collect_test_inventory import collect_inventory
from build_test_shards import build_manifest
from run_test_shard import run_shard
from aggregate_test_results import aggregate_results


def _get_external_run_dir(run_id: str) -> Path:
    """Return an external run directory outside the Git worktree."""
    runtime_dir = os.environ.get("KATTAPPA_RUNTIME_DIR")
    if runtime_dir:
        base = Path(runtime_dir) / "validation"
    else:
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            base = Path(local_app) / "Kattappa" / "validation-runs"
        else:
            import tempfile
            base = Path(tempfile.gettempdir()) / "kattappa-validation-runs"
    run_dir = base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def compute_data_digest() -> dict:
    paths = [
        PROJECT_ROOT / "backend" / "data",
        PROJECT_ROOT / "kattappa_data_engine" / "reports" / "defaults",
    ]
    k_data_dir = os.environ.get("KATTAPPA_DATA_DIR")
    if k_data_dir:
        paths.append(Path(k_data_dir))

    digests = {}
    for p in paths:
        if p.exists():
            if p.is_file():
                digests[str(p.relative_to(PROJECT_ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
            elif p.is_dir():
                for f in sorted(list(p.rglob("*"))):
                    if f.is_file() and not f.name.startswith("."):
                        try:
                            rel_p = str(f.relative_to(PROJECT_ROOT))
                        except ValueError:
                            rel_p = str(f)
                        digests[rel_p] = hashlib.sha256(f.read_bytes()).hexdigest()
    return digests


def verify_source_provenance() -> tuple[bool, str, list[str]]:
    errors = []
    try:
        head_sha = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"], text=True
        ).strip()

        # 1. Verify required runner files tracked in HEAD
        runner_files = [
            "scripts/validation/collect_test_inventory.py",
            "scripts/validation/build_test_shards.py",
            "scripts/validation/run_test_shard.py",
            "scripts/validation/aggregate_test_results.py",
            "scripts/validation/run_full_suite_sharded.py",
            "scripts/validation/test_shard_policy.yaml",
            "scripts/validation/k-r0.5-scope-policy.yaml",
            "scripts/validation/pytest_result_plugin.py",
        ]

        tracked_in_head = set(
            subprocess.check_output(
                ["git", "-C", str(PROJECT_ROOT), "ls-tree", "-r", "--name-only", "HEAD"],
                text=True,
            ).splitlines()
        )
        for f in runner_files:
            if f not in tracked_in_head:
                errors.append(f"Runner file '{f}' is not tracked in HEAD {head_sha[:8]}")

        # 2. Strict worktree check: no dirty or untracked source files
        status_lines = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
            text=True,
        ).splitlines()

        for line in status_lines:
            line_clean = line.strip()
            # Only ignore evaluation reflections (runtime-generated)
            if "evaluation/reflections/" in line_clean:
                continue
            if line_clean:
                errors.append(f"Dirty or untracked file in worktree: {line_clean}")

        return (len(errors) == 0), head_sha, errors
    except Exception as e:
        return False, "unknown", [f"Git provenance command failed: {e}"]


def run_full_sharded_suite(shard_size: int = 250):
    # --- Generate immutable run identity ---
    start_sha_pre = "unknown"
    try:
        start_sha_pre = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        pass

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"k-r0.5-A-{start_sha_pre[:8]}-{run_timestamp}"
    run_dir = _get_external_run_dir(run_id)

    print(f"=== K-R0.5 Official Release Run ===")
    print(f"Run ID: {run_id}")
    print(f"Run Directory: {run_dir}")
    print(f"Candidate Commit: {start_sha_pre[:12]}")
    print()

    # Write initial run metadata
    run_metadata = {
        "run_id": run_id,
        "run_label": "A",
        "candidate_commit": start_sha_pre,
        "branch": "codex/k-r0.5-clean",
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "status": "running",
    }
    (run_dir / "run-metadata.json").write_text(json.dumps(run_metadata, indent=2), encoding="utf-8")

    print("--- 0. Fail-Closed Source Provenance & Worktree Preflight ---")
    valid_start, start_sha, pre_errors = verify_source_provenance()
    print(f"Start Commit SHA: {start_sha[:12]}")

    pre_digest = compute_data_digest()

    if not valid_start:
        print("\n[FAILED] PROVENANCE PREFLIGHT FAILED. ABORTING RELEASE RUN.")
        for err in pre_errors:
            print(f"  - {err}")

        release_verdict = {
            "run_id": run_id,
            "verdict": "INVALID",
            "valid_for_release": False,
            "start_commit": start_sha,
            "end_commit": start_sha,
            "reason": "SOURCE_PROVENANCE_PREFLIGHT_FAILED",
            "errors": pre_errors,
        }
        (run_dir / "release-verdict.json").write_text(
            json.dumps(release_verdict, indent=2), encoding="utf-8"
        )
        run_metadata["status"] = "failed_preflight"
        run_metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
        (run_dir / "run-metadata.json").write_text(
            json.dumps(run_metadata, indent=2), encoding="utf-8"
        )
        return 3

    print("[PASSED] Provenance Preflight Passed: All runner files tracked in HEAD, 0 untracked source files.")

    print("\n--- 1. Collecting Test Inventory ---")
    n_collected, c_hash, p_hash = collect_inventory(run_dir)

    run_metadata["collection_hash"] = c_hash
    run_metadata["policy_hash"] = p_hash

    print("\n--- 2. Building Shard Manifest ---")
    n_shards, m_hash = build_manifest(run_dir, shard_size=shard_size)

    run_metadata["manifest_hash"] = m_hash
    (run_dir / "run-metadata.json").write_text(
        json.dumps(run_metadata, indent=2), encoding="utf-8"
    )

    print("\n--- 3. Executing Shards ---")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    t0 = time.time()
    for s in manifest["shards"]:
        run_shard(s, run_dir)
    total_time = time.time() - t0

    print(f"\nCompleted all {n_shards} shards in {total_time:.2f}s")

    print("\n--- 4. Post-Execution Worktree Integrity & Provenance Check ---")
    valid_end, end_sha, post_errors = verify_source_provenance()
    post_digest = compute_data_digest()

    data_changed = pre_digest != post_digest
    changed_data_paths = [
        p
        for p in set(list(pre_digest.keys()) + list(post_digest.keys()))
        if pre_digest.get(p) != post_digest.get(p)
    ]

    if start_sha != end_sha or not valid_end or data_changed:
        print("\n[FAILED] POST-EXECUTION INTEGRITY OR PROVENANCE FAILED.")
        if start_sha != end_sha:
            print(f"  - Start SHA {start_sha[:8]} != End SHA {end_sha[:8]}")
        for err in post_errors:
            print(f"  - {err}")
        if data_changed:
            print(f"  - Data mutation detected in paths: {changed_data_paths}")

    print("\n--- 5. Aggregating Test Results ---")
    test_verdict_data = aggregate_results(run_dir)

    provenance_passed = valid_start and valid_end and start_sha == end_sha and not data_changed
    final_is_pass = provenance_passed and test_verdict_data["test_verdict"] == "PASS"

    release_verdict = {
        "run_id": run_id,
        "verdict": "PASS" if final_is_pass else "FAIL",
        "valid_for_release": final_is_pass,
        "run_class": "release_candidate",
        "start_commit": start_sha,
        "end_commit": end_sha,
        "policy_hash": p_hash,
        "collection_hash": c_hash,
        "manifest_hash": m_hash,
        "provenance_verification": {
            "valid_start": valid_start,
            "valid_end": valid_end,
            "commit_match": start_sha == end_sha,
            "pre_errors": pre_errors,
            "post_errors": post_errors,
        },
        "data_integrity_verification": {
            "data_changed": data_changed,
            "changed_paths": changed_data_paths,
        },
        "test_verdict": test_verdict_data,
    }

    # SOLE author of release-verdict.json — written to EXTERNAL run directory
    (run_dir / "release-verdict.json").write_text(
        json.dumps(release_verdict, indent=2), encoding="utf-8"
    )

    run_metadata["status"] = "completed"
    run_metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    (run_dir / "run-metadata.json").write_text(
        json.dumps(run_metadata, indent=2), encoding="utf-8"
    )

    print("\n=================== FINAL RELEASE VERDICT ===================")
    print(f"RUN ID: {run_id}")
    print(f"RUN DIRECTORY: {run_dir}")
    print(f"RELEASE VERDICT: {release_verdict['verdict']}")
    print(f"VALID FOR RELEASE: {release_verdict['valid_for_release']}")
    print(f"Start Commit: {start_sha[:12]} | End Commit: {end_sha[:12]}")
    print("=============================================================\n")

    return 0 if final_is_pass else 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Kattappa K-R0.5 Sharded Full Suite Runner")
    parser.add_argument(
        "--target-tests-per-shard",
        type=int,
        default=250,
        help="Target number of test nodes per shard",
    )
    args = parser.parse_args()
    sys.exit(run_full_sharded_suite(shard_size=args.target_tests_per_shard))
