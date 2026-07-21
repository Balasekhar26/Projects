import json
import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def build_manifest(
    evidence_dir: Path,
    shard_size: int = 250,
    run_id: str = None,
    run_label: str = "A",
    candidate_commit: str = None,
    environment_fingerprint: dict = None,
    schedule_order: str = "canonical"
) -> tuple[int, str]:
    coll_file = evidence_dir / "collection.json"
    if not coll_file.exists():
        raise FileNotFoundError(f"Missing collection file at {coll_file}")

    with open(coll_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["items"]
    coll_hash = (evidence_dir / "collection-hash.txt").read_text().strip()
    p_hash = data.get("policy_hash", "unknown_policy")

    # Group by isolation class
    by_class = {
        "parallel_safe": [],
        "isolated_stateful": [],
        "exclusive_process": [],
        "browser_ui": [],
        "resource_heavy": []
    }

    for item in items:
        cls = item["isolation_class"]
        by_class.setdefault(cls, []).append(item["node_id"])

    shards = []
    shard_id = 1

    # Exclusive, browser, resource_heavy get 1-to-1 or small serial shards
    for cls in ["exclusive_process", "browser_ui", "resource_heavy"]:
        nodes = sorted(by_class[cls], reverse=(schedule_order == "alternate"))
        if nodes:
            for i in range(0, len(nodes), 100):
                chunk = nodes[i:i+100]
                shards.append({
                    "shard_id": f"shard_{shard_id:02d}_{cls}",
                    "isolation_class": cls,
                    "concurrency": 1,
                    "node_ids": chunk
                })
                shard_id += 1

    # Parallel safe and isolated stateful chunked into standard shards
    for cls in ["parallel_safe", "isolated_stateful"]:
        nodes = sorted(by_class[cls], reverse=(schedule_order == "alternate"))
        concurrency = 2 if cls == "parallel_safe" else 1
        for i in range(0, len(nodes), shard_size):
            chunk = nodes[i:i+shard_size]
            shards.append({
                "shard_id": f"shard_{shard_id:02d}_{cls}",
                "isolation_class": cls,
                "concurrency": concurrency,
                "node_ids": chunk
            })
            shard_id += 1

    # Integrity verification
    all_assigned = []
    for s in shards:
        all_assigned.extend(s["node_ids"])

    collected_set = set(item["node_id"] for item in items)
    assigned_set = set(all_assigned)

    assert len(all_assigned) == len(assigned_set), "Duplicate node IDs found in manifest!"
    assert collected_set == assigned_set, f"Mismatch between collected ({len(collected_set)}) and assigned ({len(assigned_set)}) nodes!"

    # Stage 1: manifest_core (compact, keys sorted, normalized separators)
    manifest_core = {
        "schema_version": 2,
        "run_id": run_id,
        "run_label": run_label,
        "candidate_commit": candidate_commit,
        "collection_hash": coll_hash,
        "policy_hash": p_hash,
        "environment_fingerprint": environment_fingerprint,
        "shards": shards
    }

    core_json = json.dumps(manifest_core, sort_keys=True, separators=(',', ':'))

    # Stage 2: manifest_hash = SHA256(canonical_manifest_core)
    manifest_hash = hashlib.sha256(core_json.encode("utf-8")).hexdigest()

    # Bind run identity metadata to top-level and each shard definition
    manifest_content = dict(manifest_core)
    manifest_content["manifest_hash"] = manifest_hash
    for s in manifest_content["shards"]:
        s["run_id"] = run_id
        s["run_label"] = run_label
        s["candidate_commit"] = candidate_commit
        s["collection_hash"] = coll_hash
        s["policy_hash"] = p_hash
        s["manifest_hash"] = manifest_hash

    # Final serialized write
    final_manifest_json = json.dumps(manifest_content, indent=2)

    with open(evidence_dir / "manifest.json", "w", encoding="utf-8") as f:
        f.write(final_manifest_json)

    with open(evidence_dir / "manifest-hash.txt", "w", encoding="utf-8") as f:
        f.write(manifest_hash)

    print(f"Built manifest with {len(shards)} shards covering {len(all_assigned)} nodes.")
    print(f"  Manifest hash: {manifest_hash[:12]} | Policy hash: {p_hash[:12]}")
    return len(shards), manifest_hash

if __name__ == "__main__":
    out_dir = PROJECT_ROOT / "docs" / "evidence" / "k-r0.5"
    build_manifest(out_dir)
