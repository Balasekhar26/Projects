import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def compute_policy_hash() -> str:
    policy_file = PROJECT_ROOT / "scripts" / "validation" / "test_shard_policy.yaml"
    if not policy_file.exists():
        return "default_policy"
    content = policy_file.read_bytes()
    return hashlib.sha256(content).hexdigest()

def classify_node(node_id: str) -> str:
    path_lower = node_id.lower()
    if any(k in path_lower for k in ["browser", "playwright", "gui", "ui"]):
        return "browser_ui"
    if any(k in path_lower for k in ["dev_backend_process", "runtime_readiness", "start_backend", "stop_backend", "lifecycle"]):
        return "exclusive_process"
    if any(k in path_lower for k in ["benchmark", "superbench", "stress", "hypothesis"]):
        return "resource_heavy"
    if any(k in path_lower for k in ["sqlite", "chroma", "vector", "memory", "storage", "db", "persistence", "file"]):
        return "isolated_stateful"
    return "parallel_safe"

def collect_inventory(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
    env = dict(os.environ)
    env["KATTAPPA_TEST_MODE"] = "true"

    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, env=env)
    
    raw_lines = proc.stdout.splitlines()
    node_ids = []
    for line in raw_lines:
        line = line.strip()
        if "::" in line and not line.startswith("<") and not line.startswith("="):
            node_ids.append(line)

    node_ids = sorted(list(set(node_ids)))
    p_hash = compute_policy_hash()

    items = []
    for nid in node_ids:
        source_file = nid.split("::")[0]
        cls = classify_node(nid)
        items.append({
            "node_id": nid,
            "source_file": source_file,
            "isolation_class": cls,
            "estimated_duration_seconds": 1.0 if cls == "parallel_safe" else 3.0
        })

    payload = {
        "count": len(items),
        "policy_hash": p_hash,
        "items": items
    }
    collection_content = json.dumps(payload, indent=2)
    collection_hash = hashlib.sha256(collection_content.encode("utf-8")).hexdigest()

    with open(output_dir / "collection.json", "w", encoding="utf-8") as f:
        f.write(collection_content)

    with open(output_dir / "collection-hash.txt", "w", encoding="utf-8") as f:
        f.write(collection_hash)

    print(f"Collected {len(items)} unique test node IDs. Collection hash: {collection_hash[:12]} | Policy hash: {p_hash[:12]}")
    return len(items), collection_hash, p_hash

if __name__ == "__main__":
    out_dir = PROJECT_ROOT / "docs" / "evidence" / "k-r0.5"
    collect_inventory(out_dir)
