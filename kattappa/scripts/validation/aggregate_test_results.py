import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def aggregate_results(evidence_dir: Path) -> dict:
    coll_file = evidence_dir / "collection.json"
    man_file = evidence_dir / "manifest.json"
    id_file = evidence_dir / "run-identity.json"
    shards_dir = evidence_dir / "shards"

    if not coll_file.exists() or not man_file.exists() or not id_file.exists():
        raise FileNotFoundError("Missing collection.json, manifest.json, or run-identity.json in evidence directory")

    collection = json.loads(coll_file.read_text(encoding="utf-8"))
    manifest = json.loads(man_file.read_text(encoding="utf-8"))
    run_identity = json.loads(id_file.read_text(encoding="utf-8"))

    # Canonical identity values from run-identity.json
    run_id = run_identity.get("run_id")
    candidate_commit = run_identity.get("candidate_commit")
    collection_hash = run_identity.get("collection_hash")
    policy_hash = run_identity.get("policy_hash")
    manifest_core_hash = run_identity.get("manifest_core_hash")
    manifest_file_hash = run_identity.get("manifest_file_hash")

    # 1. Verification of hash strings
    def validate_sha256(val: str, name: str):
        if not val:
            raise ValueError(f"{name} is null or empty")
        if len(val) != 64:
            raise ValueError(f"{name} has wrong length: {len(val)} (expected 64)")
        import re
        if not re.match(r"^[0-9a-fA-F]{64}$", val):
            raise ValueError(f"{name} is not a valid hexadecimal string")

    validate_sha256(manifest_core_hash, "manifest_core_hash")
    validate_sha256(manifest_file_hash, "manifest_file_hash")

    # 2. Recompute manifest_core_hash independently
    import copy
    import hashlib
    reconstructed_core = copy.deepcopy(manifest)
    reconstructed_core.pop("manifest_core_hash", None)
    for s in reconstructed_core.get("shards", []):
        s.pop("run_id", None)
        s.pop("run_label", None)
        s.pop("candidate_commit", None)
        s.pop("collection_hash", None)
        s.pop("policy_hash", None)
        s.pop("manifest_core_hash", None)
        s.pop("manifest_file_hash", None)

    reconstructed_json = json.dumps(reconstructed_core, sort_keys=True, separators=(',', ':'))
    recomputed_core_hash = hashlib.sha256(reconstructed_json.encode("utf-8")).hexdigest()

    # 3. Recompute manifest_file_hash independently
    manifest_bytes = man_file.read_bytes()
    recomputed_file_hash = hashlib.sha256(manifest_bytes).hexdigest()

    if recomputed_core_hash != manifest_core_hash:
        raise ValueError(f"Recomputed manifest_core_hash mismatch: {recomputed_core_hash} != {manifest_core_hash}")
    if recomputed_file_hash != manifest_file_hash:
        raise ValueError(f"Recomputed manifest_file_hash mismatch: {recomputed_file_hash} != {manifest_file_hash}")

    # Check sidecar files
    core_sidecar = evidence_dir / "manifest-core-hash.txt"
    file_sidecar = evidence_dir / "manifest-file-hash.txt"
    if not core_sidecar.exists() or not file_sidecar.exists():
        raise FileNotFoundError("Missing manifest sidecar hash files")
    if core_sidecar.read_text(encoding="utf-8").strip() != manifest_core_hash:
        raise ValueError("manifest-core-hash.txt sidecar value mismatch")
    if file_sidecar.read_text(encoding="utf-8").strip() != manifest_file_hash:
        raise ValueError("manifest-file-hash.txt sidecar value mismatch")

    manifest_shard_ids = {s["shard_id"] for s in manifest["shards"]}
    collected_node_ids = set(item["node_id"] for item in collection["items"])

    assigned_node_ids_list = []
    manifest_shards_map = {}
    for s in manifest["shards"]:
        assigned_node_ids_list.extend(s["node_ids"])
        manifest_shards_map[s["shard_id"]] = s

    assigned_node_ids = set(assigned_node_ids_list)

    executed_node_ids = set()
    attempted_node_ids = set()
    completed_node_ids = set()

    executed_node_ids_list = []
    attempted_node_ids_list = []
    completed_node_ids_list = []

    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_skipped = 0
    total_xfailed = 0
    total_xpassed = 0

    crashed_shards = 0
    timed_out_shards = 0
    failed_test_shards = 0
    interrupted_shards = 0
    internal_error_shards = 0
    usage_error_shards = 0
    empty_shards = 0
    process_crash_shards = 0

    total_duration = 0.0
    processed_shard_ids = set()

    if shards_dir.exists():
        for sdir in shards_dir.iterdir():
            if not sdir.is_dir():
                continue
            res_file = sdir / "shard-result.json"
            if not res_file.exists():
                crashed_shards += 1
                process_crash_shards += 1
                continue

            try:
                sres = json.loads(res_file.read_text(encoding="utf-8"))
            except Exception:
                crashed_shards += 1
                process_crash_shards += 1
                continue

            # Strict cross-run and stale result validations
            s_id = sres.get("shard_id")
            if not s_id:
                raise ValueError("Shard result is missing shard_id field")

            # Rejection of duplicate shard result processing
            if s_id in processed_shard_ids:
                raise ValueError(f"Duplicate shard result processed for shard_id: {s_id}")
            processed_shard_ids.add(s_id)

            if sres.get("run_id") != run_id:
                raise ValueError(f"Shard {s_id} has mismatching run_id: {sres.get('run_id')} != {run_id}")
            if sres.get("candidate_commit") != candidate_commit:
                raise ValueError(f"Shard {s_id} has mismatching candidate_commit: {sres.get('candidate_commit')} != {candidate_commit}")
            if sres.get("collection_hash") != collection_hash:
                raise ValueError(f"Shard {s_id} has mismatching collection_hash: {sres.get('collection_hash')} != {collection_hash}")
            if sres.get("policy_hash") != policy_hash:
                raise ValueError(f"Shard {s_id} has mismatching policy_hash: {sres.get('policy_hash')} != {policy_hash}")
            if sres.get("manifest_core_hash") != manifest_core_hash:
                raise ValueError(f"Shard {s_id} has mismatching manifest_core_hash: {sres.get('manifest_core_hash')} != {manifest_core_hash}")
            if sres.get("manifest_file_hash") != manifest_file_hash:
                raise ValueError(f"Shard {s_id} has mismatching manifest_file_hash: {sres.get('manifest_file_hash')} != {manifest_file_hash}")

            if s_id not in manifest_shard_ids:
                raise ValueError(f"Shard ID {s_id} is not defined in the current manifest")

            # Shard independent verify:
            manifest_shard = manifest_shards_map[s_id]
            shard_assigned_nodes = set(manifest_shard.get("node_ids", []))
            shard_result_assigned = set(sres.get("assigned_node_ids", []))
            if shard_assigned_nodes != shard_result_assigned:
                raise ValueError(f"Shard {s_id} assigned_node_ids mismatch with manifest")

            s_executed = sres.get("executed_node_ids", [])
            s_attempted = sres.get("attempted_node_ids", sres.get("executed_node_ids", []))
            s_completed = sres.get("completed_node_ids", sres.get("executed_node_ids", []))

            if not set(s_executed).issubset(shard_assigned_nodes):
                raise ValueError(f"Shard {s_id} executed_node_ids contains unassigned nodes")
            if not set(s_attempted).issubset(shard_assigned_nodes):
                raise ValueError(f"Shard {s_id} attempted_node_ids contains unassigned nodes")
            if not set(s_completed).issubset(shard_assigned_nodes):
                raise ValueError(f"Shard {s_id} completed_node_ids contains unassigned nodes")

            executed_node_ids_list.extend(s_executed)
            attempted_node_ids_list.extend(s_attempted)
            completed_node_ids_list.extend(s_completed)

            executed_node_ids.update(s_executed)
            attempted_node_ids.update(s_attempted)
            completed_node_ids.update(s_completed)

            total_duration += sres.get("duration_seconds", 0.0)
            total_passed += sres.get("passed", 0)
            total_failed += sres.get("failed", 0)
            total_errors += sres.get("errors", 0)
            total_skipped += sres.get("skipped", 0)
            total_xfailed += sres.get("xfailed", 0)
            total_xpassed += sres.get("xpassed", 0)

            if sres.get("timed_out", False):
                timed_out_shards += 1

            exit_code = sres.get("exit_code", 0)
            if exit_code == 1:
                failed_test_shards += 1
            elif exit_code == 2:
                interrupted_shards += 1
            elif exit_code == 3:
                internal_error_shards += 1
            elif exit_code == 4:
                usage_error_shards += 1
            elif exit_code == 5:
                empty_shards += 1
            elif exit_code not in (0, 5):
                crashed_shards += 1

    missing_shard_ids = sorted(list(manifest_shard_ids - processed_shard_ids))
    unexpected_shard_ids = sorted(list(processed_shard_ids - manifest_shard_ids))

    from collections import Counter
    exec_counts = Counter(executed_node_ids_list)
    attempt_counts = Counter(attempted_node_ids_list)
    complete_counts = Counter(completed_node_ids_list)

    duplicate_executions = sum(count - 1 for count in exec_counts.values() if count > 1)
    duplicate_attempts = sum(count - 1 for count in attempt_counts.values() if count > 1)
    duplicate_completions = sum(count - 1 for count in complete_counts.values() if count > 1)

    # Exact Node Set Verification
    missing_from_manifest = len(collected_node_ids - assigned_node_ids)
    duplicate_assignments = len(assigned_node_ids_list) - len(assigned_node_ids)
    unexecuted_nodes = len(assigned_node_ids - executed_node_ids)
    unattempted_nodes = len(assigned_node_ids - attempted_node_ids)
    unexpected_executions = len(executed_node_ids - assigned_node_ids)

    is_test_pass = (
        missing_from_manifest == 0 and
        duplicate_assignments == 0 and
        unexecuted_nodes == 0 and
        unattempted_nodes == 0 and
        unexpected_executions == 0 and
        duplicate_executions == 0 and
        duplicate_attempts == 0 and
        duplicate_completions == 0 and
        len(missing_shard_ids) == 0 and
        len(unexpected_shard_ids) == 0 and
        collected_node_ids == assigned_node_ids and
        assigned_node_ids == attempted_node_ids and
        attempted_node_ids == completed_node_ids and
        total_failed == 0 and
        total_errors == 0 and
        crashed_shards == 0 and
        timed_out_shards == 0 and
        interrupted_shards == 0 and
        internal_error_shards == 0
    )

    test_verdict = {
        "test_verdict": "PASS" if is_test_pass else "FAIL",
        "policy_hash": manifest.get("policy_hash"),
        "collection_hash": collection.get("collection_hash", manifest.get("collection_hash")),
        "manifest_core_hash": manifest_core_hash,
        "manifest_file_hash": manifest_file_hash,
        "total_nodes_collected": len(collected_node_ids),
        "total_nodes_assigned": len(assigned_node_ids),
        "total_nodes_attempted": len(attempted_node_ids),
        "total_nodes_executed": len(executed_node_ids),
        "total_nodes_completed": len(completed_node_ids),
        "node_set_verification": {
            "missing_from_manifest": missing_from_manifest,
            "duplicate_assignments": duplicate_assignments,
            "unexecuted_nodes": unexecuted_nodes,
            "unattempted_nodes": unattempted_nodes,
            "unexpected_executions": unexpected_executions,
            "duplicate_executions": duplicate_executions,
            "duplicate_attempts": duplicate_attempts,
            "duplicate_completions": duplicate_completions
        },
        "shard_set_verification": {
            "missing_shard_ids": missing_shard_ids,
            "unexpected_shard_ids": unexpected_shard_ids
        },
        "test_outcomes": {
            "passed": total_passed,
            "failed": total_failed,
            "errors": total_errors,
            "skipped": total_skipped,
            "xfailed": total_xfailed,
            "xpassed": total_xpassed
        },
        "shard_outcomes": {
            "total_shards": len(manifest["shards"]),
            "failed_test_shards": failed_test_shards,
            "crashed_shards": crashed_shards,
            "timed_out_shards": timed_out_shards,
            "interrupted_shards": interrupted_shards,
            "internal_error_shards": internal_error_shards,
            "usage_error_shards": usage_error_shards,
            "empty_shards": empty_shards,
            "process_crash_shards": process_crash_shards
        },
        "total_duration_seconds": round(total_duration, 2)
    }

    final_path = evidence_dir / "test-verdict.json"
    atomic_write_json(final_path, test_verdict)

    print("\n=================== TEST VERDICT SUMMARY ===================")
    print(f"VERDICT: {test_verdict['test_verdict']}")
    print(f"Collected: {len(collected_node_ids)} | Assigned: {len(assigned_node_ids)} | Executed: {len(executed_node_ids)}")
    print(f"Passed: {total_passed} | Failed: {total_failed} | Errors: {total_errors} | Skipped: {total_skipped}")
    print(f"Unexecuted Nodes: {unexecuted_nodes} | Crashed Shards: {crashed_shards} | Timed Out: {timed_out_shards}")
    print("============================================================\n")

    return test_verdict

def atomic_write_json(path: Path, payload: dict):
    import os
    tmp_path = path.with_suffix(".json.tmp") if path.suffix == ".json" else Path(str(path) + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with open(tmp_path, "r", encoding="utf-8") as f:
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
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
    out_dir = PROJECT_ROOT / "docs" / "evidence" / "k-r0.5"
    aggregate_results(out_dir)
