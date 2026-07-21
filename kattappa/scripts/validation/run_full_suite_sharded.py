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
    try:
        tracked_files = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "ls-files"], text=True
        ).splitlines()
    except Exception:
        tracked_files = []

    target_prefixes = (
        "backend/data/",
        "kattappa_data_engine/reports/defaults/"
    )

    digests = {}
    for f_rel in tracked_files:
        norm_rel = f_rel.replace("\\", "/")
        # If it matches the prefix or starts with it
        if any(norm_rel.startswith(p) for p in target_prefixes):
            abs_p = PROJECT_ROOT / norm_rel
            if abs_p.is_file():
                try:
                    digests[norm_rel] = hashlib.sha256(abs_p.read_bytes()).hexdigest()
                except Exception:
                    pass
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

        release_active = (os.environ.get("KATTAPPA_RELEASE_RUN_ACTIVE") == "1")
        for line in status_lines:
            line_clean = line.strip()
            if not release_active:
                if "evaluation/reflections/" in line_clean:
                    continue
                if "requirements.txt" in line_clean and not "kattappa/" in line_clean:
                    continue
            if line_clean:
                errors.append(f"Dirty or untracked file in worktree: {line_clean}")

        return (len(errors) == 0), head_sha, errors
    except Exception as e:
        return False, "unknown", [f"Git provenance command failed: {e}"]


def run_full_sharded_suite(shard_size: int = 250, run_label: str = "A", schedule_order: str = "canonical"):
    active = os.environ.get("KATTAPPA_RELEASE_RUN_ACTIVE")
    launcher_pid = os.environ.get("KATTAPPA_RELEASE_LAUNCHER_PID")
    if active == "1" and launcher_pid != str(os.getpid()):
        print("[CRITICAL] Recursive run guard triggered. Aborting execution.")
        sys.exit(5)
    os.environ["KATTAPPA_RELEASE_RUN_ACTIVE"] = "1"
    os.environ["KATTAPPA_RELEASE_LAUNCHER_PID"] = str(os.getpid())

    # --- Generate immutable run identity ---
    start_sha_pre = "unknown"
    try:
        start_sha_pre = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        pass

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"k-r0.5-{run_label}-{start_sha_pre[:8]}-{run_timestamp}"
    run_dir = _get_external_run_dir(run_id)

    print(f"=== K-R0.5 Official Release Run ===")
    print(f"Run ID: {run_id}")
    print(f"Run Directory: {run_dir}")
    print(f"Candidate Commit: {start_sha_pre[:12]}")
    print()

    # Write initial run metadata
    run_metadata = {
        "run_id": run_id,
        "run_label": run_label,
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
            "status": "invalid_provenance",
            "start_commit": start_sha,
            "end_commit": start_sha,
            "reason": "SOURCE_PROVENANCE_PREFLIGHT_FAILED",
            "errors": pre_errors,
        }
        (run_dir / "release-verdict.json").write_text(
            json.dumps(release_verdict, indent=2), encoding="utf-8"
        )
        run_metadata["status"] = "invalid_provenance"
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
    n_shards, m_core_hash, m_file_hash = build_manifest(
        run_dir,
        shard_size=shard_size,
        run_id=run_id,
        run_label=run_label,
        candidate_commit=start_sha_pre,
        environment_fingerprint=run_metadata,
        schedule_order=schedule_order
    )

    run_metadata["manifest_core_hash"] = m_core_hash
    run_metadata["manifest_file_hash"] = m_file_hash
    (run_dir / "run-metadata.json").write_text(
        json.dumps(run_metadata, indent=2), encoding="utf-8"
    )

    print("\n--- 3. Executing Shards ---")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    # Load authoritative run identity from sidecar (not from manifest.json)
    run_identity = json.loads((run_dir / "run-identity.json").read_text(encoding="utf-8"))

    # Validate sidecar consistency
    assert run_identity["manifest_core_hash"] == m_core_hash, "run-identity manifest_core_hash mismatch"
    assert run_identity["manifest_file_hash"] == m_file_hash, "run-identity manifest_file_hash mismatch"

    t0 = time.time()
    for s in manifest["shards"]:
        # 8. Timeout must be mandatory in official manifests
        if os.environ.get("KATTAPPA_RELEASE_RUN_ACTIVE") == "1" and "timeout_seconds" not in s:
            raise RuntimeError("Official shard is missing policy-resolved timeout")

        # Construct execution_shard by merging manifest shard with authoritative identity
        execution_shard = {
            **s,
            "run_id": run_identity["run_id"],
            "run_label": run_identity["run_label"],
            "candidate_commit": run_identity["candidate_commit"],
            "collection_hash": run_identity["collection_hash"],
            "policy_hash": run_identity["policy_hash"],
            "manifest_core_hash": run_identity["manifest_core_hash"],
            "manifest_file_hash": run_identity["manifest_file_hash"],
            "environment_hash": run_identity["environment_hash"],
        }
        run_shard(execution_shard, run_dir)
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

    # Calculate runtime writes and escapes
    runtime_files_created = 0
    runtime_files_modified = 0
    runtime_writes_outside_assigned_roots = []
    
    # Any post-execution status warnings outside reflections become escapes
    if not valid_end:
        for err in post_errors:
            runtime_writes_outside_assigned_roots.append(err)

    workspaces_base = run_dir / "workspaces"
    if workspaces_base.exists():
        for f in workspaces_base.rglob("*"):
            if f.is_file():
                runtime_files_created += 1

    print("\n--- 5. Aggregating Test Results ---")
    invalid_artifacts = False
    artifact_errors = []
    try:
        test_verdict_data = aggregate_results(run_dir)
    except Exception as e:
        print(f"\n[FAILED] ARTIFACT AGGREGATION OR IDENTITY MISMATCH: {e}")
        test_verdict_data = {
            "test_verdict": "FAIL",
            "error": str(e)
        }
        invalid_artifacts = True
        artifact_errors = [str(e)]

    provenance_passed = valid_start and valid_end and start_sha == end_sha and not data_changed and len(runtime_writes_outside_assigned_roots) == 0
    final_is_pass = provenance_passed and not invalid_artifacts and test_verdict_data.get("test_verdict") == "PASS"

    # Define explicit terminal status
    if not valid_start or not valid_end or start_sha != end_sha:
        status = "invalid_provenance"
    elif data_changed or len(runtime_writes_outside_assigned_roots) > 0:
        status = "invalid_provenance"
    elif invalid_artifacts:
        status = "invalid_artifacts"
    elif test_verdict_data.get("test_verdict") == "TIMEOUT" or test_verdict_data.get("shard_outcomes", {}).get("timed_out_shards", 0) > 0:
        status = "timed_out"
    elif test_verdict_data.get("test_verdict") == "PASS":
        status = "passed"
    else:
        status = "failed_tests"

    release_verdict = {
        "run_id": run_id,
        "verdict": "PASS" if final_is_pass else ("INVALID" if (not provenance_passed or invalid_artifacts) else "FAIL"),
        "valid_for_release": final_is_pass,
        "run_class": "release_candidate",
        "status": status,
        "start_commit": start_sha,
        "end_commit": end_sha,
        "policy_hash": p_hash,
        "collection_hash": c_hash,
        "manifest_core_hash": m_core_hash,
        "manifest_file_hash": m_file_hash,
        "provenance_verification": {
            "valid_start": valid_start,
            "valid_end": valid_end,
            "commit_match": start_sha == end_sha,
            "pre_errors": pre_errors,
            "post_errors": post_errors,
        },
        "data_integrity_verification": {
            "tracked_repository_data_changed": data_changed,
            "runtime_files_created": runtime_files_created,
            "runtime_files_modified": runtime_files_modified,
            "runtime_writes_outside_assigned_roots": runtime_writes_outside_assigned_roots,
        },
        "test_verdict": test_verdict_data,
    }

    if invalid_artifacts:
        release_verdict["artifact_errors"] = artifact_errors

    # Atomic write for release-verdict.json
    rv_final = run_dir / "release-verdict.json"
    atomic_write_json(rv_final, release_verdict)

    # Atomic write for run-metadata.json
    run_metadata["status"] = status
    run_metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    rm_final = run_dir / "run-metadata.json"
    atomic_write_json(rm_final, run_metadata)

    # Reopen and compute hashes of all final files to create RUN_COMPLETE marker
    def compute_file_sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    try:
        collection_sha = compute_file_sha256(run_dir / "collection.json")
        manifest_sha = compute_file_sha256(run_dir / "manifest.json")
        test_verdict_sha = compute_file_sha256(run_dir / "test-verdict.json")
        release_verdict_sha = compute_file_sha256(run_dir / "release-verdict.json")
        run_metadata_sha = compute_file_sha256(run_dir / "run-metadata.json")

        # Compute artifact tree SHA-256 (hashing the sorted names & hashes of all non-complete files in run_dir)
        all_files = []
        for root_dir, _, files in os.walk(run_dir):
            for file in files:
                if file != "RUN_COMPLETE":
                    fp = Path(root_dir) / file
                    rel_p = fp.relative_to(run_dir).as_posix()
                    file_sha = compute_file_sha256(fp)
                    all_files.append((rel_p, file_sha))
        all_files.sort()
        tree_hash_payload = "\n".join(f"{name}:{sha}" for name, sha in all_files)
        artifact_tree_sha256 = hashlib.sha256(tree_hash_payload.encode("utf-8")).hexdigest()

        # RUN_COMPLETE needs verdict binding
        run_complete = {
            "run_id": run_id,
            "candidate_commit": start_sha,
            "status": status,
            "verdict": release_verdict['verdict'],
            "valid_for_release": final_is_pass,
            "release_verdict_sha256": release_verdict_sha,
            "test_verdict_sha256": test_verdict_sha,
            "manifest_file_sha256": manifest_sha,
            "artifact_tree_sha256": artifact_tree_sha256,
            "completed_at": run_metadata["completed_at"]
        }

        # Write RUN_COMPLETE atomically
        rc_final = run_dir / "RUN_COMPLETE"
        atomic_write_json(rc_final, run_complete)
    except Exception as exc:
        raise RuntimeError(f"RUN_COMPLETE generation or verification failed: {exc}")

    print("\n=================== FINAL RELEASE VERDICT ===================")
    print(f"RUN ID: {run_id}")
    print(f"RUN DIRECTORY: {run_dir}")
    print(f"RELEASE VERDICT: {release_verdict['verdict']}")
    print(f"STATUS: {release_verdict['status']}")
    print(f"VALID FOR RELEASE: {release_verdict['valid_for_release']}")
    print(f"Start Commit: {start_sha[:12]} | End Commit: {end_sha[:12]}")
    print("=============================================================\n")

    return 0 if final_is_pass else 1

def atomic_write_json(path: Path, payload: dict):
    import os
    tmp_path = path.with_suffix(".json.tmp") if path.suffix == ".json" else Path(str(path) + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    try:
        val = json.loads(tmp_path.read_text(encoding="utf-8"))
        assert isinstance(val, (dict, list))
    except Exception as exc:
        raise RuntimeError(f"Failed to validate temp JSON at {tmp_path}: {exc}")
    os.replace(tmp_path, path)
    try:
        val2 = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(val2, (dict, list))
    except Exception as exc:
        raise RuntimeError(f"Failed to validate final JSON at {path}: {exc}")
    parent = path.parent
    try:
        fd = os.open(str(parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Kattappa K-R0.5 Sharded Full Suite Runner")
    parser.add_argument(
        "--target-tests-per-shard",
        type=int,
        default=250,
        help="Target number of test nodes per shard",
    )
    parser.add_argument(
        "--run-label",
        type=str,
        default="A",
        choices=["A", "B", "C", "D"],
        help="Label for the run (A, B, C, or D)"
    )
    parser.add_argument(
        "--schedule-order",
        type=str,
        default="canonical",
        choices=["canonical", "repeat", "alternate"],
        help="Scheduling order for shard assignment"
    )
    args = parser.parse_args()
    sys.exit(run_full_sharded_suite(
        shard_size=args.target_tests_per_shard,
        run_label=args.run_label,
        schedule_order=args.schedule_order
    ))
