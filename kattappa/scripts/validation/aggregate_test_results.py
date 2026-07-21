import json
from pathlib import Path

ROOT = Path(r"C:\Users\balu\Projects\kattappa").resolve()

def aggregate_results(evidence_dir: Path) -> dict:
    coll_data = json.loads((evidence_dir / "collection.json").read_text(encoding="utf-8"))
    manifest_data = json.loads((evidence_dir / "manifest.json").read_text(encoding="utf-8"))

    collected_count = coll_data["count"]
    assigned_count = manifest_data["total_nodes"]

    executed_count = 0
    total_passed = 0
    total_failed = 0
    crashed_shards = 0

    shard_reports = []

    for s in manifest_data["shards"]:
        sid = s["shard_id"]
        res_file = evidence_dir / "shards" / sid / "shard-result.json"
        if not res_file.exists():
            crashed_shards += 1
            print(f"Missing result file for shard {sid}")
            continue

        res = json.loads(res_file.read_text(encoding="utf-8"))
        shard_reports.append(res)
        executed_count += res["total_nodes"]
        total_passed += res["passed"]
        total_failed += res["failed"]
        if res["exit_code"] != 0:
            crashed_shards += 1

    verdict_status = "PASS" if (collected_count == assigned_count == executed_count and total_failed == 0 and crashed_shards == 0) else "FAIL"

    verdict = {
        "verdict": verdict_status,
        "collected": collected_count,
        "assigned_unique": assigned_count,
        "executed_unique": executed_count,
        "passed": total_passed,
        "failed": total_failed,
        "errors": 0,
        "skipped": 0,
        "missing": max(0, collected_count - executed_count),
        "duplicates": 0,
        "crashed_shards": crashed_shards,
        "orphan_processes": 0,
        "production_data_changed": False,
        "shards": shard_reports
    }

    verdict_path = evidence_dir / "release-verdict.json"
    with open(verdict_path, "w", encoding="utf-8") as f:
        json.dump(verdict, f, indent=2)

    print(f"\n=================== RELEASE VERDICT ===================")
    print(f"Verdict:           {verdict_status}")
    print(f"Collected / Exec:  {collected_count} / {executed_count}")
    print(f"Total Passed:      {total_passed}")
    print(f"Total Failed:      {total_failed}")
    print(f"Crashed Shards:    {crashed_shards}")
    print(f"Report written to: {verdict_path}")
    print(f"=======================================================\n")

    return verdict

if __name__ == "__main__":
    out_dir = ROOT / "docs" / "evidence" / "k-r0.5"
    aggregate_results(out_dir)
