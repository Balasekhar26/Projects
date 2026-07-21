import json
import hashlib
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def compute_data_digest() -> str:
    data_dir = PROJECT_ROOT / "backend" / "data"
    if not data_dir.exists():
        return "no_data_dir"
    
    digests = []
    for p in sorted(data_dir.rglob("*")):
        if p.is_file() and not p.name.endswith(".log") and not p.name.endswith(".tmp"):
            try:
                rel = p.relative_to(PROJECT_ROOT).as_posix()
                content = p.read_bytes()
                h = hashlib.sha256(content).hexdigest()
                digests.append(f"{rel}:{h}")
            except Exception:
                pass
    return hashlib.sha256("\n".join(digests).encode("utf-8")).hexdigest()

def aggregate_results(evidence_dir: Path) -> dict:
    coll_file = evidence_dir / "collection.json"
    manifest_file = evidence_dir / "manifest.json"

    if not coll_file.exists() or not manifest_file.exists():
        return {
            "verdict": "FAIL",
            "reason": "Missing collection.json or manifest.json",
            "valid_for_release": False
        }

    with open(coll_file, "r", encoding="utf-8") as f:
        coll_data = json.load(f)

    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    collected_set = set(item["node_id"] for item in coll_data.get("items", []))
    manifest_shards = manifest_data.get("shards", [])

    assigned_multiset = Counter()
    for s in manifest_shards:
        for nid in s.get("node_ids", []):
            assigned_multiset[nid] += 1

    executed_multiset = Counter()
    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_skipped = 0
    crashed_shards = 0
    timed_out_shards = 0
    total_duration = 0.0

    shards_dir = evidence_dir / "shards"
    
    for s in manifest_shards:
        sid = s["shard_id"]
        res_file = shards_dir / sid / "shard-result.json"
        if not res_file.exists():
            crashed_shards += 1
            continue

        try:
            with open(res_file, "r", encoding="utf-8") as rf:
                sres = json.load(rf)

            if sres.get("timed_out"):
                timed_out_shards += 1

            for nid in sres.get("executed_node_ids", []):
                executed_multiset[nid] += 1

            total_passed += sres.get("passed", 0)
            total_failed += sres.get("failed", 0)
            total_errors += sres.get("errors", 0)
            total_skipped += sres.get("skipped", 0)
            total_duration += sres.get("duration_seconds", 0.0)

            if sres.get("exit_code") not in (0, 5):
                if not sres.get("timed_out"):
                    crashed_shards += 1
        except Exception:
            crashed_shards += 1

    assigned_set = set(assigned_multiset.keys())
    executed_set = set(executed_multiset.keys())

    missing_from_manifest = sorted(list(collected_set - assigned_set))
    duplicate_assignments = sorted([k for k, v in assigned_multiset.items() if v > 1])
    unexecuted_nodes = sorted(list(assigned_set - executed_set))
    unexpected_executions = sorted(list(executed_set - assigned_set))
    duplicate_executions = sorted([k for k, v in executed_multiset.items() if v > 1])

    is_pass = (
        len(missing_from_manifest) == 0 and
        len(duplicate_assignments) == 0 and
        len(unexecuted_nodes) == 0 and
        len(unexpected_executions) == 0 and
        len(duplicate_executions) == 0 and
        total_failed == 0 and
        total_errors == 0 and
        crashed_shards == 0 and
        timed_out_shards == 0
    )

    verdict_payload = {
        "verdict": "PASS" if is_pass else "FAIL",
        "valid_for_release": is_pass,
        "policy_hash": manifest_data.get("policy_hash", "unknown"),
        "collection_hash": manifest_data.get("collection_hash", "unknown"),
        "total_nodes_collected": len(collected_set),
        "total_nodes_assigned": len(assigned_set),
        "total_nodes_executed": len(executed_set),
        "node_set_verification": {
            "missing_from_manifest": len(missing_from_manifest),
            "duplicate_assignments": len(duplicate_assignments),
            "unexecuted_nodes": len(unexecuted_nodes),
            "unexpected_executions": len(unexpected_executions),
            "duplicate_executions": len(duplicate_executions)
        },
        "test_outcomes": {
            "passed": total_passed,
            "failed": total_failed,
            "errors": total_errors,
            "skipped": total_skipped
        },
        "shard_outcomes": {
            "total_shards": len(manifest_shards),
            "crashed_shards": crashed_shards,
            "timed_out_shards": timed_out_shards
        },
        "total_duration_seconds": round(total_duration, 2)
    }

    with open(evidence_dir / "release-verdict.json", "w", encoding="utf-8") as f:
        json.dump(verdict_payload, f, indent=2)

    print("\n=================== RELEASE VERDICT SUMMARY ===================")
    print(f"VERDICT: {verdict_payload['verdict']}")
    print(f"Collected: {len(collected_set)} | Executed: {len(executed_set)} | Passed: {total_passed} | Failed: {total_failed} | Errors: {total_errors}")
    print(f"Unexecuted: {len(unexecuted_nodes)} | Duplicates: {len(duplicate_executions)} | Crashed Shards: {crashed_shards}")
    print("===============================================================")

    return verdict_payload

if __name__ == "__main__":
    out_dir = PROJECT_ROOT / "docs" / "evidence" / "k-r0.5"
    aggregate_results(out_dir)
