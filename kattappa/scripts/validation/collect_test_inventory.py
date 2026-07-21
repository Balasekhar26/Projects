import sys
import os
import re
import json
import yaml
import hashlib
import platform
import subprocess
from pathlib import Path
from dataclasses import dataclass

PROJECT_ROOT = Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class ShardPolicy:
    schema_version: int
    policy_name: str
    default_isolation_class: str
    isolation_classes: dict
    path_rules: dict

def load_shard_policy() -> ShardPolicy:
    policy_file = PROJECT_ROOT / "scripts" / "validation" / "test_shard_policy.yaml"
    if not policy_file.exists():
        raise FileNotFoundError(f"Shard policy file missing: {policy_file}")
    data = yaml.safe_load(policy_file.read_text(encoding="utf-8"))
    return ShardPolicy(
        schema_version=data.get("schema_version", 1),
        policy_name=data.get("policy_name", "default_policy"),
        default_isolation_class=data.get("default_isolation_class", "isolated_stateful"),
        isolation_classes=data.get("isolation_classes", {}),
        path_rules=data.get("path_rules", {})
    )

def compute_policy_hash() -> str:
    policy_file = PROJECT_ROOT / "scripts" / "validation" / "test_shard_policy.yaml"
    return hashlib.sha256(policy_file.read_bytes()).hexdigest()

def classify_node_with_policy(node_id: str, policy: ShardPolicy) -> str:
    norm_id = node_id.lower()
    
    # 1. Evaluate Path Rules from YAML policy
    for cls_name, patterns in policy.path_rules.items():
        for pat in patterns:
            if re.search(pat.lower(), norm_id):
                return cls_name

    # 2. Default fallback must be isolated_stateful (NOT parallel_safe)
    return policy.default_isolation_class

def classify_node(node_id: str) -> str:
    policy = load_shard_policy()
    return classify_node_with_policy(node_id, policy)

def get_environment_fingerprint() -> dict:
    head_sha = "unknown"
    try:
        head_sha = subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        pass
    
    return {
        "commit_sha": head_sha,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "pytest_version": subprocess.check_output([sys.executable, "-m", "pytest", "--version"], text=True).strip(),
        "platform": platform.platform()
    }

def collect_inventory(output_dir: Path) -> tuple[int, str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    policy = load_shard_policy()
    p_hash = compute_policy_hash()

    print(f"Collecting test inventory with policy '{policy.policy_name}' (default={policy.default_isolation_class})...")
    
    cmd = [sys.executable, "-m", "pytest", "backend/tests", "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)

    if proc.returncode != 0:
        print(f"\n[FAILED] Pytest collection failed with exit code {proc.returncode}")
        print(proc.stderr)
        raise RuntimeError(f"Pytest collection failed with exit code {proc.returncode}")

    node_ids_raw = [line.strip() for line in proc.stdout.splitlines() if "::" in line and not line.startswith("=")]
    
    # Check duplicate node IDs before deduplicating
    node_id_counts = {}
    for nid in node_ids_raw:
        node_id_counts[nid] = node_id_counts.get(nid, 0) + 1
        
    duplicate_node_ids = [nid for nid, count in node_id_counts.items() if count > 1]
    if duplicate_node_ids:
        print(f"\n[FAILED] Collection error: Duplicate node IDs detected: {len(duplicate_node_ids)}")
        raise RuntimeError(f"Duplicate node IDs detected in test collection: {duplicate_node_ids[:5]}")

    unique_nodes = sorted(list(set(node_ids_raw)))
    
    items = []
    for nid in unique_nodes:
        source_file = nid.split("::")[0]
        iso_cls = classify_node_with_policy(nid, policy)
        items.append({
            "node_id": nid,
            "source_file": source_file,
            "isolation_class": iso_cls
        })

    env_fp = get_environment_fingerprint()
    collection_payload = {
        "count": len(items),
        "raw_collected_count": len(node_ids_raw),
        "unique_collected_count": len(unique_nodes),
        "duplicate_node_ids": duplicate_node_ids,
        "policy_hash": p_hash,
        "environment_fingerprint": env_fp,
        "items": items
    }

    coll_bytes = json.dumps(collection_payload, indent=2).encode("utf-8")
    c_hash = hashlib.sha256(coll_bytes).hexdigest()

    (output_dir / "collection.json").write_bytes(coll_bytes)
    (output_dir / "collection-hash.txt").write_text(c_hash, encoding="utf-8")

    print(f"Collected {len(items)} unique test node IDs. Collection hash: {c_hash[:12]} | Policy hash: {p_hash[:12]}")
    return len(items), c_hash, p_hash

if __name__ == "__main__":
    out_dir = PROJECT_ROOT / "docs" / "evidence" / "k-r0.5"
    collect_inventory(out_dir)
