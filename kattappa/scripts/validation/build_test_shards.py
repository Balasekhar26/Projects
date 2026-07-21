import json
import hashlib
from pathlib import Path
from collect_test_inventory import load_shard_policy

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def build_manifest(
    evidence_dir: Path,
    shard_size: int = 250,
    run_id: str = None,
    run_label: str = "A",
    candidate_commit: str = None,
    environment_fingerprint: dict = None,
    schedule_order: str = "canonical"
) -> tuple[int, str, str]:
    coll_file = evidence_dir / "collection.json"
    if not coll_file.exists():
        raise FileNotFoundError(f"Missing collection file at {coll_file}")

    with open(coll_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["items"]
    coll_hash = (evidence_dir / "collection-hash.txt").read_text(encoding="utf-8").strip()
    p_hash = data.get("policy_hash", "unknown_policy")

    policy = load_shard_policy()

    # Load shard-duration-baseline.json
    baseline_file = PROJECT_ROOT / "scripts" / "validation" / "shard-duration-baseline.json"
    baseline_data = {}
    if baseline_file.exists():
        try:
            baseline_list = json.loads(baseline_file.read_text(encoding="utf-8"))
            for entry in baseline_list:
                baseline_data[entry["node_id"]] = entry
        except Exception:
            pass

    # Filter out validation harness tests first
    validation_nodes = []
    other_items = []
    for item in items:
        if "test_sharded_validation.py" in item["node_id"]:
            validation_nodes.append(item["node_id"])
        else:
            other_items.append(item)

    # Group other items by isolation class
    by_class = {
        "parallel_safe": [],
        "isolated_stateful": [],
        "exclusive_process": [],
        "browser_ui": [],
        "resource_heavy": []
    }

    for item in other_items:
        cls = item["isolation_class"]
        by_class.setdefault(cls, []).append(item["node_id"])

    shards = []
    shard_id = 1

    def get_timeout_for_class(cls_name: str, shard_nodes: list) -> tuple[int, str]:
        timeout_policy = policy.timeout_policy.get(cls_name, {})
        base_sec = timeout_policy.get("base_seconds", 300)
        max_sec = timeout_policy.get("maximum_seconds", 600)
        
        has_history = False
        total_history_duration = 0.0
        for node in shard_nodes:
            if node in baseline_data:
                has_history = True
                node_median = baseline_data[node].get("median_seconds", 0.0)
                total_history_duration += max(node_median, 0.5)
                
        if has_history:
            estimated_duration = total_history_duration
            source = "history"
        else:
            estimated_duration = 0.0
            source = "class_default"
            
        resolved_timeout = min(max_sec, max(base_sec, int(estimated_duration * 3)))
        return resolved_timeout, source

    # Exclusive, browser, resource_heavy get 1-to-1 or small serial shards
    for cls in ["exclusive_process", "browser_ui", "resource_heavy"]:
        nodes = sorted(by_class[cls], reverse=(schedule_order == "alternate"))
        if nodes:
            for i in range(0, len(nodes), 100):
                chunk = nodes[i:i+100]
                timeout_sec, source = get_timeout_for_class(cls, chunk)
                shards.append({
                    "shard_id": f"shard_{shard_id:02d}_{cls}",
                    "isolation_class": cls,
                    "concurrency": 1,
                    "timeout_seconds": timeout_sec,
                    "duration_estimation_source": source,
                    "node_ids": chunk
                })
                shard_id += 1

    # Parallel safe and isolated stateful chunked into standard shards
    for cls in ["parallel_safe", "isolated_stateful"]:
        nodes = sorted(by_class[cls], reverse=(schedule_order == "alternate"))
        concurrency = 2 if cls == "parallel_safe" else 1
        for i in range(0, len(nodes), shard_size):
            chunk = nodes[i:i+shard_size]
            timeout_sec, source = get_timeout_for_class(cls, chunk)
            shards.append({
                "shard_id": f"shard_{shard_id:02d}_{cls}",
                "isolation_class": cls,
                "concurrency": concurrency,
                "timeout_seconds": timeout_sec,
                "duration_estimation_source": source,
                "node_ids": chunk
            })
            shard_id += 1

    # Add the dedicated validation harness shard last
    if validation_nodes:
        val_nodes_sorted = sorted(validation_nodes, reverse=(schedule_order == "alternate"))
        timeout_sec, source = get_timeout_for_class("exclusive_process", val_nodes_sorted)
        shards.append({
            "shard_id": "shard_validation_harness",
            "isolation_class": "exclusive_process",
            "concurrency": 1,
            "timeout_seconds": timeout_sec,
            "duration_estimation_source": source,
            "node_ids": val_nodes_sorted
        })

    # Integrity verification
    all_assigned = []
    for s in shards:
        all_assigned.extend(s["node_ids"])

    collected_set = set(item["node_id"] for item in items)
    assigned_set = set(all_assigned)

    assert len(all_assigned) == len(assigned_set), "Duplicate node IDs found in manifest!"
    assert collected_set == assigned_set, f"Mismatch between collected ({len(collected_set)}) and assigned ({len(assigned_set)}) nodes!"

    # Stage 1: manifest_core
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

    # Stage 2: manifest_core_hash
    manifest_core_hash = hashlib.sha256(core_json.encode("utf-8")).hexdigest()

    # Bind manifest_core_hash to each shard definition
    manifest_content = dict(manifest_core)
    manifest_content["manifest_core_hash"] = manifest_core_hash
    for s in manifest_content["shards"]:
        s["run_id"] = run_id
        s["run_label"] = run_label
        s["candidate_commit"] = candidate_commit
        s["collection_hash"] = coll_hash
        s["policy_hash"] = p_hash
        s["manifest_core_hash"] = manifest_core_hash

    # Final serialized write of manifest.json
    manifest_file_path = evidence_dir / "manifest.json"
    atomic_write_json(manifest_file_path, manifest_content)

    # Compute manifest_file_hash on the final manifest.json bytes
    manifest_file_bytes = manifest_file_path.read_bytes()
    manifest_file_hash = hashlib.sha256(manifest_file_bytes).hexdigest()

    # Write manifest-core-hash.txt and manifest-file-hash.txt
    core_hash_path = evidence_dir / "manifest-core-hash.txt"
    file_hash_path = evidence_dir / "manifest-file-hash.txt"
    atomic_write_text(core_hash_path, manifest_core_hash)
    atomic_write_text(file_hash_path, manifest_file_hash)

    # Write run-identity.json
    env_json = json.dumps(environment_fingerprint or {}, sort_keys=True, separators=(',', ':'))
    env_hash = hashlib.sha256(env_json.encode("utf-8")).hexdigest()

    run_identity = {
        "run_id": run_id or "",
        "run_label": run_label or "",
        "candidate_commit": candidate_commit or "",
        "collection_hash": coll_hash or "",
        "policy_hash": p_hash or "",
        "manifest_core_hash": manifest_core_hash,
        "manifest_file_hash": manifest_file_hash,
        "environment_hash": env_hash
    }
    identity_path = evidence_dir / "run-identity.json"
    atomic_write_json(identity_path, run_identity)

    # Reopen and verify all four files
    try:
        m_loaded = json.loads(manifest_file_path.read_text(encoding="utf-8"))
        assert m_loaded["manifest_core_hash"] == manifest_core_hash

        i_loaded = json.loads(identity_path.read_text(encoding="utf-8"))
        assert i_loaded["manifest_core_hash"] == manifest_core_hash
        assert i_loaded["manifest_file_hash"] == manifest_file_hash

        assert core_hash_path.read_text(encoding="utf-8").strip() == manifest_core_hash
        assert file_hash_path.read_text(encoding="utf-8").strip() == manifest_file_hash
    except Exception as exc:
        raise RuntimeError(f"Post-manifest generation verification failed: {exc}")

    # Inject the identity values into each in-memory shard execution request
    for s in shards:
        s["run_id"] = run_id
        s["run_label"] = run_label
        s["candidate_commit"] = candidate_commit
        s["collection_hash"] = coll_hash
        s["policy_hash"] = p_hash
        s["manifest_core_hash"] = manifest_core_hash
        s["manifest_file_hash"] = manifest_file_hash

    print(f"Built manifest with {len(shards)} shards covering {len(all_assigned)} nodes.")
    print(f"  Manifest core hash: {manifest_core_hash[:12]} | manifest file hash: {manifest_file_hash[:12]}")
    return len(shards), manifest_core_hash, manifest_file_hash

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

def atomic_write_text(path: Path, content: str):
    import os
    tmp_path = Path(str(path) + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    with open(tmp_path, "r", encoding="utf-8") as f:
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    assert tmp_path.read_text(encoding="utf-8") == content
    os.replace(tmp_path, path)
    assert path.read_text(encoding="utf-8") == content
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
    build_manifest(out_dir)
