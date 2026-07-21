import json
import pytest
import tempfile
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\balu\Projects\kattappa").resolve()
if str(ROOT / "scripts" / "validation") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "validation"))

from collect_test_inventory import collect_inventory, classify_node, compute_policy_hash
from build_test_shards import build_manifest
from aggregate_test_results import aggregate_results

def test_inventory_node_classification():
    assert classify_node("backend/tests/test_browser_action.py::test_click") == "browser_ui"
    assert classify_node("backend/tests/test_dev_backend_process.py::test_start") == "exclusive_process"
    assert classify_node("backend/tests/test_benchmark.py::test_run") == "resource_heavy"
    assert classify_node("backend/tests/test_sqlite_store.py::test_db") == "isolated_stateful"
    assert classify_node("backend/tests/test_simple_math.py::test_add") == "parallel_safe"

def test_policy_hash_computation():
    p_hash = compute_policy_hash()
    assert isinstance(p_hash, str)
    assert len(p_hash) == 64

def test_manifest_building_and_node_assignment_integrity():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        sample_items = [
            {"node_id": f"backend/tests/test_a.py::test_{i}", "source_file": "backend/tests/test_a.py", "isolation_class": "parallel_safe"}
            for i in range(10)
        ] + [
            {"node_id": "backend/tests/test_b.py::test_exec", "source_file": "backend/tests/test_b.py", "isolation_class": "exclusive_process"}
        ]
        
        coll_json = json.dumps({"count": len(sample_items), "policy_hash": "mock_p_hash", "items": sample_items})
        (tmp_path / "collection.json").write_text(coll_json, encoding="utf-8")
        (tmp_path / "collection-hash.txt").write_text("mock_hash_123", encoding="utf-8")

        n_shards, m_hash = build_manifest(tmp_path, shard_size=5)
        
        assert n_shards > 0
        assert (tmp_path / "manifest.json").exists()

        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["policy_hash"] == "mock_p_hash"
        assigned_nodes = []
        for s in manifest["shards"]:
            assigned_nodes.extend(s["node_ids"])

        assert len(assigned_nodes) == len(sample_items)
        assert set(assigned_nodes) == set(item["node_id"] for item in sample_items)

def test_aggregate_results_detects_crashed_and_missing_shards():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        coll_json = json.dumps({"count": 2, "policy_hash": "p1", "items": [{"node_id": "t1", "isolation_class": "parallel_safe"}, {"node_id": "t2", "isolation_class": "parallel_safe"}]})
        manifest_json = json.dumps({
            "total_nodes": 2,
            "policy_hash": "p1",
            "shards": [
                {"shard_id": "shard_01", "isolation_class": "parallel_safe", "node_ids": ["t1"]},
                {"shard_id": "shard_02", "isolation_class": "parallel_safe", "node_ids": ["t2"]}
            ]
        })
        
        (tmp_path / "collection.json").write_text(coll_json, encoding="utf-8")
        (tmp_path / "manifest.json").write_text(manifest_json, encoding="utf-8")

        # Shard 1 passed
        s1_dir = tmp_path / "shards" / "shard_01"
        s1_dir.mkdir(parents=True)
        (s1_dir / "shard-result.json").write_text(json.dumps({
            "shard_id": "shard_01", "total_nodes": 1, "passed": 1, "failed": 0, "exit_code": 0, "duration_seconds": 1.0
        }))

        # Shard 2 missing -> triggers FAIL
        verdict = aggregate_results(tmp_path)
        assert verdict["verdict"] == "FAIL"
        assert verdict["crashed_shards"] == 1
