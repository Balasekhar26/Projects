import json
import pytest
import tempfile
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "validation"))

from collect_test_inventory import (
    collect_inventory,
    classify_node,
    classify_node_with_policy,
    load_shard_policy,
    compute_policy_hash,
    ShardPolicy
)
from build_test_shards import build_manifest
from aggregate_test_results import aggregate_results
from verify_commit_scope import is_path_allowed, load_scope_policy

# 1. Policy controls classification
def test_policy_yaml_controls_classification():
    policy = ShardPolicy(
        schema_version=1,
        policy_name="test_policy",
        default_isolation_class="isolated_stateful",
        isolation_classes={},
        path_rules={
            "exclusive_process": [".*custom_exclusive_test.*"],
            "browser_ui": [".*custom_ui_test.*"]
        }
    )
    assert classify_node_with_policy("backend/tests/custom_exclusive_test.py::test_run", policy) == "exclusive_process"
    assert classify_node_with_policy("backend/tests/custom_ui_test.py::test_run", policy) == "browser_ui"

# 2. Unknown test defaults to isolated_stateful
def test_unknown_test_defaults_to_isolated_stateful():
    policy = ShardPolicy(
        schema_version=1,
        policy_name="test_policy",
        default_isolation_class="isolated_stateful",
        isolation_classes={},
        path_rules={}
    )
    assert classify_node_with_policy("backend/tests/test_unknown_random_foo.py::test_bar", policy) == "isolated_stateful"

# 3. Policy hash computation changes with file content
def test_policy_hash_changes_with_content():
    p_hash = compute_policy_hash()
    assert isinstance(p_hash, str) and len(p_hash) == 64

# 4. Scope policy allowlist checks
def test_scope_policy_allowlist_matching():
    policy = {
        "allowed_paths": [
            "backend/core/rbil.py",
            "scripts/validation/*"
        ],
        "conditionally_allowed_paths": [
            "scripts/dev/_backend_process.py"
        ]
    }
    assert is_path_allowed("backend/core/rbil.py", policy) is True
    assert is_path_allowed("scripts/validation/run_test_shard.py", policy) is True
    assert is_path_allowed("scripts/dev/_backend_process.py", policy) is True
    assert is_path_allowed("backend/unapproved/cognitive_hack.py", policy) is False

# 5. Manifest building and node assignment integrity
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

# 6. Aggregator writes ONLY test-verdict.json (NEVER release-verdict.json)
def test_aggregator_writes_only_test_verdict_json():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        coll_json = json.dumps({
            "count": 1,
            "policy_hash": "p1",
            "items": [{"node_id": "t1", "isolation_class": "parallel_safe"}]
        })
        manifest_json = json.dumps({
            "total_nodes": 1,
            "policy_hash": "p1",
            "collection_hash": "c1",
            "shards": [{"shard_id": "shard_01", "isolation_class": "parallel_safe", "node_ids": ["t1"]}]
        })
        
        (tmp_path / "collection.json").write_text(coll_json, encoding="utf-8")
        (tmp_path / "collection-hash.txt").write_text("c1", encoding="utf-8")
        (tmp_path / "manifest.json").write_text(manifest_json, encoding="utf-8")

        s1_dir = tmp_path / "shards" / "shard_01"
        s1_dir.mkdir(parents=True)
        (s1_dir / "shard-result.json").write_text(json.dumps({
            "shard_id": "shard_01",
            "isolation_class": "parallel_safe",
            "total_nodes_assigned": 1,
            "total_nodes_executed": 1,
            "executed_node_ids": ["t1"],
            "passed": 1, "failed": 0, "errors": 0, "skipped": 0,
            "exit_code": 0, "timed_out": False, "duration_seconds": 1.0
        }))

        verdict = aggregate_results(tmp_path)
        assert verdict["test_verdict"] == "PASS"
        assert (tmp_path / "test-verdict.json").exists()
        assert not (tmp_path / "release-verdict.json").exists()
        assert "valid_for_release" not in verdict

# 7. Unexecuted node triggers FAIL in test-verdict
def test_aggregate_results_detects_unexecuted_nodes():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        coll_json = json.dumps({
            "count": 2,
            "policy_hash": "p1",
            "items": [{"node_id": "t1", "isolation_class": "parallel_safe"}, {"node_id": "t2", "isolation_class": "parallel_safe"}]
        })
        manifest_json = json.dumps({
            "total_nodes": 2,
            "policy_hash": "p1",
            "collection_hash": "c1",
            "shards": [
                {"shard_id": "shard_01", "isolation_class": "parallel_safe", "node_ids": ["t1"]},
                {"shard_id": "shard_02", "isolation_class": "parallel_safe", "node_ids": ["t2"]}
            ]
        })
        
        (tmp_path / "collection.json").write_text(coll_json, encoding="utf-8")
        (tmp_path / "collection-hash.txt").write_text("c1", encoding="utf-8")
        (tmp_path / "manifest.json").write_text(manifest_json, encoding="utf-8")

        s1_dir = tmp_path / "shards" / "shard_01"
        s1_dir.mkdir(parents=True)
        (s1_dir / "shard-result.json").write_text(json.dumps({
            "shard_id": "shard_01",
            "isolation_class": "parallel_safe",
            "total_nodes_assigned": 1,
            "total_nodes_executed": 1,
            "executed_node_ids": ["t1"],
            "passed": 1, "failed": 0, "errors": 0, "skipped": 0,
            "exit_code": 0, "timed_out": False, "duration_seconds": 1.0
        }))

        verdict = aggregate_results(tmp_path)
        assert verdict["test_verdict"] == "FAIL"
        assert verdict["node_set_verification"]["unexecuted_nodes"] == 1

# 8. Exit code breakdown
def test_exit_code_breakdown_in_aggregator():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        coll_json = json.dumps({"count": 1, "policy_hash": "p1", "items": [{"node_id": "t1", "isolation_class": "parallel_safe"}]})
        manifest_json = json.dumps({"total_nodes": 1, "shards": [{"shard_id": "shard_01", "isolation_class": "parallel_safe", "node_ids": ["t1"]}]})
        
        (tmp_path / "collection.json").write_text(coll_json, encoding="utf-8")
        (tmp_path / "collection-hash.txt").write_text("c1", encoding="utf-8")
        (tmp_path / "manifest.json").write_text(manifest_json, encoding="utf-8")

        s1_dir = tmp_path / "shards" / "shard_01"
        s1_dir.mkdir(parents=True)
        (s1_dir / "shard-result.json").write_text(json.dumps({
            "shard_id": "shard_01",
            "total_nodes_assigned": 1,
            "executed_node_ids": ["t1"],
            "passed": 0, "failed": 1, "errors": 0, "skipped": 0,
            "exit_code": 1, "timed_out": False, "duration_seconds": 1.0
        }))

        verdict = aggregate_results(tmp_path)
        assert verdict["shard_outcomes"]["failed_test_shards"] == 1
        assert verdict["shard_outcomes"]["crashed_shards"] == 0
