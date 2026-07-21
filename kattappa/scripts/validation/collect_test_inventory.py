import sys
import os
import re
import json
import yaml
import hashlib
import platform
import configparser
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
    timeout_policy: dict = None

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
        path_rules=data.get("path_rules", {}),
        timeout_policy=data.get("timeout_policy", {})
    )

def compute_policy_hash() -> str:
    policy_file = PROJECT_ROOT / "scripts" / "validation" / "test_shard_policy.yaml"
    return hashlib.sha256(policy_file.read_bytes()).hexdigest()

def classify_node_with_policy(node_id: str, policy: ShardPolicy) -> str:
    norm_id = node_id.lower()
    for cls_name, patterns in policy.path_rules.items():
        for pat in patterns:
            if re.search(pat.lower(), norm_id):
                return cls_name
    return policy.default_isolation_class

def classify_node(node_id: str) -> str:
    policy = load_shard_policy()
    return classify_node_with_policy(node_id, policy)

def load_canonical_testpaths() -> list[str]:
    """Parse pytest.ini to extract the canonical testpaths."""
    ini_path = PROJECT_ROOT / "pytest.ini"
    if not ini_path.exists():
        raise FileNotFoundError(f"pytest.ini missing at {ini_path}")

    config = configparser.ConfigParser()
    config.read(ini_path, encoding="utf-8")

    testpaths_str = config.get("pytest", "testpaths", fallback="")
    testpaths = [tp.strip() for tp in testpaths_str.strip().splitlines() if tp.strip()]
    if not testpaths:
        raise RuntimeError("pytest.ini contains no testpaths entries")
    return testpaths

def get_environment_fingerprint() -> dict:
    head_sha = "unknown"
    try:
        head_sha = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        pass

    return {
        "commit_sha": head_sha,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "pytest_version": subprocess.check_output(
            [sys.executable, "-m", "pytest", "--version"], text=True
        ).strip(),
        "platform": platform.platform(),
    }

def _collect_root(root: str) -> list[str]:
    """Collect test node IDs from a single test root."""
    cmd = [sys.executable, "-m", "pytest", root, "--collect-only", "-q", "--ignore=docs"]
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"\n[FAILED] Pytest collection for root '{root}' failed with exit code {proc.returncode}")
        print(proc.stderr)
        raise RuntimeError(f"Pytest collection for root '{root}' failed with exit code {proc.returncode}")
    return [line.strip() for line in proc.stdout.splitlines() if "::" in line and not line.startswith("=")]

def collect_inventory(output_dir: Path) -> tuple[int, str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    policy = load_shard_policy()
    p_hash = compute_policy_hash()
    testpaths = load_canonical_testpaths()

    print(f"Collecting test inventory with policy '{policy.policy_name}' across {len(testpaths)} canonical testpaths...")

    # --- Per-root collection with full node-set persistence ---
    per_root = {}
    root_union = set()
    for tp in testpaths:
        nodes = _collect_root(tp)
        node_set = sorted(set(nodes))
        node_set_hash = hashlib.sha256("\n".join(node_set).encode("utf-8")).hexdigest()
        per_root[tp] = {
            "count": len(node_set),
            "node_ids": node_set,
            "node_set_hash": node_set_hash,
        }
        root_union.update(node_set)
        print(f"  - Root '{tp}': {len(node_set)} unique test nodes")

    # --- Full combined collection ---
    full_cmd = [sys.executable, "-m", "pytest"] + testpaths + ["--collect-only", "-q", "--ignore=docs"]
    full_proc = subprocess.run(full_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if full_proc.returncode != 0:
        print(f"\n[FAILED] Full pytest collection failed with exit code {full_proc.returncode}")
        print(full_proc.stderr)
        raise RuntimeError(f"Full pytest collection failed with exit code {full_proc.returncode}")

    node_ids_raw = [
        line.strip()
        for line in full_proc.stdout.splitlines()
        if "::" in line and not line.startswith("=")
    ]

    # Duplicate check
    node_id_counts: dict[str, int] = {}
    for nid in node_ids_raw:
        node_id_counts[nid] = node_id_counts.get(nid, 0) + 1
    duplicate_node_ids = [nid for nid, count in node_id_counts.items() if count > 1]
    if duplicate_node_ids:
        print(f"\n[FAILED] Collection error: Duplicate node IDs detected: {len(duplicate_node_ids)}")
        raise RuntimeError(f"Duplicate node IDs detected: {duplicate_node_ids[:5]}")

    unique_nodes = sorted(set(node_ids_raw))

    # --- Root-union verification ---
    sorted_root_union = sorted(root_union)
    cross_root_dupes: list[str] = []
    # Detect nodes present in more than one root
    seen_roots: dict[str, list[str]] = {}
    for tp, rdata in per_root.items():
        for nid in rdata["node_ids"]:
            seen_roots.setdefault(nid, []).append(tp)
    cross_root_dupes = sorted([nid for nid, roots in seen_roots.items() if len(roots) > 1])

    missing_from_union = sorted(set(unique_nodes) - root_union)
    unexpected_in_union = sorted(root_union - set(unique_nodes))

    root_union_verification = {
        "union_count": len(sorted_root_union),
        "full_collection_count": len(unique_nodes),
        "union_equals_full": set(sorted_root_union) == set(unique_nodes),
        "cross_root_duplicates": cross_root_dupes,
        "missing_from_root_union": missing_from_union,
        "unexpected_in_root_union": unexpected_in_union,
    }

    if not root_union_verification["union_equals_full"]:
        print(f"\n[FAILED] Root union ({len(sorted_root_union)}) != full collection ({len(unique_nodes)})")
        print(f"  Missing from union: {len(missing_from_union)}")
        print(f"  Unexpected in union: {len(unexpected_in_union)}")
        raise RuntimeError("Canonical test-root union does not match full collection")

    if cross_root_dupes:
        print(f"\n[FAILED] Cross-root duplicate node IDs detected: {len(cross_root_dupes)}")
        raise RuntimeError(f"Cross-root duplicate node IDs detected: {cross_root_dupes[:10]}")

    # --- Classify nodes ---
    items = []
    for nid in unique_nodes:
        source_file = nid.split("::")[0]
        iso_cls = classify_node_with_policy(nid, policy)
        items.append({
            "node_id": nid,
            "source_file": source_file,
            "isolation_class": iso_cls,
        })

    env_fp = get_environment_fingerprint()
    collection_payload = {
        "count": len(items),
        "raw_collected_count": len(node_ids_raw),
        "unique_collected_count": len(unique_nodes),
        "canonical_testpaths": testpaths,
        "per_root": per_root,
        "root_union_verification": root_union_verification,
        "duplicate_node_ids": duplicate_node_ids,
        "policy_hash": p_hash,
        "environment_fingerprint": env_fp,
        "items": items,
    }

    coll_bytes = json.dumps(collection_payload, indent=2).encode("utf-8")
    c_hash = hashlib.sha256(coll_bytes).hexdigest()

    (output_dir / "collection.json").write_bytes(coll_bytes)
    (output_dir / "collection-hash.txt").write_text(c_hash, encoding="utf-8")

    print(f"Collected {len(items)} unique test node IDs across all canonical testpaths.")
    print(f"  Collection hash: {c_hash[:12]} | Policy hash: {p_hash[:12]}")
    print(f"  Root union verified: {root_union_verification['union_equals_full']}")
    return len(items), c_hash, p_hash


if __name__ == "__main__":
    out_dir = PROJECT_ROOT / "docs" / "evidence" / "k-r0.5"
    collect_inventory(out_dir)
