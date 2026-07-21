import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def aggregate_results(evidence_dir: Path) -> dict:
    coll_file = evidence_dir / "collection.json"
    man_file = evidence_dir / "manifest.json"
    shards_dir = evidence_dir / "shards"

    if not coll_file.exists() or not man_file.exists():
        raise FileNotFoundError("Missing collection.json or manifest.json in evidence directory")

    collection = json.loads(coll_file.read_text(encoding="utf-8"))
    manifest = json.loads(man_file.read_text(encoding="utf-8"))

    # Canonical identity values from manifest
    run_id = manifest.get("run_id")
    candidate_commit = manifest.get("candidate_commit")
    collection_hash = manifest.get("collection_hash")
    policy_hash = manifest.get("policy_hash")
    manifest_hash = manifest.get("manifest_hash")

    manifest_shard_ids = {s["shard_id"] for s in manifest["shards"]}

    collected_node_ids = set(item["node_id"] for item in collection["items"])

    assigned_node_ids_list = []
    for s in manifest["shards"]:
        assigned_node_ids_list.extend(s["node_ids"])

    assigned_node_ids = set(assigned_node_ids_list)

    executed_node_ids = set()
    attempted_node_ids = set()
    completed_node_ids = set()

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
            if sres.get("manifest_hash") != manifest_hash:
                raise ValueError(f"Shard {s_id} has mismatching manifest_hash: {sres.get('manifest_hash')} != {manifest_hash}")

            if s_id not in manifest_shard_ids:
                raise ValueError(f"Shard ID {s_id} is not defined in the current manifest")

            total_duration += sres.get("duration_seconds", 0.0)

            # Node sets
            s_executed = set(sres.get("executed_node_ids", []))
            s_attempted = set(sres.get("attempted_node_ids", sres.get("executed_node_ids", [])))
            s_completed = set(sres.get("completed_node_ids", sres.get("executed_node_ids", [])))

            executed_node_ids.update(s_executed)
            attempted_node_ids.update(s_attempted)
            completed_node_ids.update(s_completed)

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

    # Exact Node Set Verification
    missing_from_manifest = len(collected_node_ids - assigned_node_ids)
    duplicate_assignments = len(assigned_node_ids_list) - len(assigned_node_ids)
    unexecuted_nodes = len(assigned_node_ids - executed_node_ids)
    unattempted_nodes = len(assigned_node_ids - attempted_node_ids)
    unexpected_executions = len(executed_node_ids - assigned_node_ids)
    duplicate_executions = len(executed_node_ids) - len(set(executed_node_ids))

    is_test_pass = (
        missing_from_manifest == 0 and
        duplicate_assignments == 0 and
        unexecuted_nodes == 0 and
        unexpected_executions == 0 and
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
            "duplicate_executions": duplicate_executions
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

    # Write ONLY test-verdict.json (never release-verdict.json)
    with open(evidence_dir / "test-verdict.json", "w", encoding="utf-8") as f:
        json.dump(test_verdict, f, indent=2)

    print("\n=================== TEST VERDICT SUMMARY ===================")
    print(f"VERDICT: {test_verdict['test_verdict']}")
    print(f"Collected: {len(collected_node_ids)} | Assigned: {len(assigned_node_ids)} | Executed: {len(executed_node_ids)}")
    print(f"Passed: {total_passed} | Failed: {total_failed} | Errors: {total_errors} | Skipped: {total_skipped}")
    print(f"Unexecuted Nodes: {unexecuted_nodes} | Crashed Shards: {crashed_shards} | Timed Out: {timed_out_shards}")
    print("============================================================\n")

    return test_verdict

if __name__ == "__main__":
    out_dir = PROJECT_ROOT / "docs" / "evidence" / "k-r0.5"
    aggregate_results(out_dir)
