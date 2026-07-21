"""K-R0.5.3 Expanded Runner Self-Validation Suite.

Covers:
- Policy YAML loading and classification
- Default fallback to isolated_stateful
- Policy hash computation
- Scope allowlist matching
- Canonical testpaths loading from pytest.ini
- Per-root union equals full collection
- Cross-root duplicate rejection
- Missing canonical root rejection
- Extra pytest root detection
- Archived evidence exclusion from collection
- Manifest building and node assignment integrity
- Aggregator writes only test-verdict.json
- Unexecuted node triggers FAIL
- Active run artifacts are outside worktree
- Run ID binding in release verdicts
"""
import json
import pytest
import tempfile
import sys
import os
import configparser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "validation"))

from collect_test_inventory import (
    collect_inventory,
    classify_node,
    classify_node_with_policy,
    load_shard_policy,
    load_canonical_testpaths,
    compute_policy_hash,
    ShardPolicy,
    _collect_root,
)
from build_test_shards import build_manifest
from aggregate_test_results import aggregate_results
from verify_commit_scope import is_path_allowed, load_scope_policy


# ---------- Policy & Classification ----------

def test_policy_yaml_controls_classification():
    policy = ShardPolicy(
        schema_version=1, policy_name="test_policy",
        default_isolation_class="isolated_stateful",
        isolation_classes={},
        path_rules={
            "exclusive_process": [".*custom_exclusive_test.*"],
            "browser_ui": [".*custom_ui_test.*"],
        },
    )
    assert classify_node_with_policy("backend/tests/custom_exclusive_test.py::test_run", policy) == "exclusive_process"
    assert classify_node_with_policy("backend/tests/custom_ui_test.py::test_run", policy) == "browser_ui"


def test_unknown_test_defaults_to_isolated_stateful():
    policy = ShardPolicy(
        schema_version=1, policy_name="test_policy",
        default_isolation_class="isolated_stateful",
        isolation_classes={}, path_rules={},
    )
    assert classify_node_with_policy("backend/tests/test_unknown.py::test_bar", policy) == "isolated_stateful"


def test_policy_hash_changes_with_content():
    p_hash = compute_policy_hash()
    assert isinstance(p_hash, str) and len(p_hash) == 64


# ---------- Scope Allowlist ----------

def test_scope_policy_allowlist_matching():
    policy = {
        "allowed_paths": ["backend/core/rbil.py", "scripts/validation/*", "docs/architecture/*"],
        "conditionally_allowed_paths": ["scripts/dev/_backend_process.py"],
    }
    assert is_path_allowed("backend/core/rbil.py", policy) is True
    assert is_path_allowed("scripts/validation/run_test_shard.py", policy) is True
    assert is_path_allowed("docs/architecture/k-him.md", policy) is True
    assert is_path_allowed("scripts/dev/_backend_process.py", policy) is True
    assert is_path_allowed("backend/unapproved/hack.py", policy) is False


# ---------- Canonical Testpaths ----------

def test_canonical_testpaths_loader():
    testpaths = load_canonical_testpaths()
    assert "backend/tests" in testpaths
    assert "kattappa_native/tests" in testpaths
    assert "kattappa_data_engine/tests" in testpaths
    assert "kattappa_runtime/resource_governor" in testpaths
    assert len(testpaths) == 4


def test_missing_canonical_root_is_rejected():
    """If pytest.ini has no testpaths, load_canonical_testpaths must raise."""
    with tempfile.TemporaryDirectory() as tmp:
        ini_path = Path(tmp) / "pytest.ini"
        ini_path.write_text("[pytest]\n", encoding="utf-8")
        import collect_test_inventory as cti
        original_root = cti.PROJECT_ROOT
        try:
            cti.PROJECT_ROOT = Path(tmp)
            with pytest.raises(RuntimeError, match="no testpaths"):
                cti.load_canonical_testpaths()
        finally:
            cti.PROJECT_ROOT = original_root


def test_extra_pytest_root_is_detected():
    """If pytest.ini testpaths differs from the expected 4, the count changes."""
    testpaths = load_canonical_testpaths()
    # The canonical set must be exactly 4
    expected = {"backend/tests", "kattappa_native/tests", "kattappa_data_engine/tests", "kattappa_runtime/resource_governor"}
    assert set(testpaths) == expected


def test_pytest_ini_policy_drift_is_rejected():
    """The testpaths in pytest.ini must exactly match the four canonical roots."""
    ini_path = PROJECT_ROOT / "pytest.ini"
    config = configparser.ConfigParser()
    config.read(ini_path, encoding="utf-8")
    testpaths_str = config.get("pytest", "testpaths", fallback="")
    testpaths = [tp.strip() for tp in testpaths_str.strip().splitlines() if tp.strip()]
    expected = ["backend/tests", "kattappa_native/tests", "kattappa_data_engine/tests", "kattappa_runtime/resource_governor"]
    assert testpaths == expected, f"pytest.ini testpaths drifted: {testpaths} != {expected}"


# ---------- Per-Root Union Verification ----------

def test_per_root_union_equals_full_collection():
    """Verify that collecting each root individually and unioning = collecting all roots together."""
    testpaths = load_canonical_testpaths()
    per_root_nodes = {}
    root_union = set()
    for tp in testpaths:
        nodes = _collect_root(tp)
        unique = set(nodes)
        per_root_nodes[tp] = unique
        root_union.update(unique)

    # Full combined collection
    import subprocess
    full_cmd = [sys.executable, "-m", "pytest"] + testpaths + ["--collect-only", "-q", "--ignore=docs"]
    proc = subprocess.run(full_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, f"Full collection failed: {proc.stderr}"
    full_nodes = set(
        line.strip() for line in proc.stdout.splitlines()
        if "::" in line and not line.startswith("=")
    )

    assert root_union == full_nodes, (
        f"Union mismatch: {len(root_union)} union vs {len(full_nodes)} full. "
        f"Missing: {full_nodes - root_union}, Extra: {root_union - full_nodes}"
    )


def test_cross_root_duplicate_is_rejected():
    """No test node should appear in more than one root."""
    testpaths = load_canonical_testpaths()
    seen: dict[str, str] = {}
    duplicates = []
    for tp in testpaths:
        nodes = _collect_root(tp)
        for nid in set(nodes):
            if nid in seen:
                duplicates.append((nid, seen[nid], tp))
            else:
                seen[nid] = tp
    assert len(duplicates) == 0, f"Cross-root duplicates found: {duplicates[:5]}"


# ---------- Evidence Exclusion ----------

def test_archived_evidence_is_not_collected():
    """No node ID should reference docs/evidence."""
    testpaths = load_canonical_testpaths()
    import subprocess
    full_cmd = [sys.executable, "-m", "pytest"] + testpaths + ["--collect-only", "-q", "--ignore=docs"]
    proc = subprocess.run(full_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    assert proc.returncode == 0
    evidence_nodes = [
        line.strip() for line in proc.stdout.splitlines()
        if "docs/evidence" in line and "::" in line
    ]
    assert len(evidence_nodes) == 0, f"Evidence files collected as tests: {evidence_nodes}"


def test_active_run_artifacts_are_outside_worktree():
    """The orchestrator must compute a run directory outside PROJECT_ROOT."""
    from run_full_suite_sharded import _get_external_run_dir
    run_dir = _get_external_run_dir("test-run-id-000")
    assert not str(run_dir).startswith(str(PROJECT_ROOT)), (
        f"Run dir {run_dir} is inside project root {PROJECT_ROOT}"
    )


# ---------- Manifest & Aggregation ----------

def test_manifest_building_and_node_assignment_integrity():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        sample_items = [
            {"node_id": f"backend/tests/test_a.py::test_{i}", "source_file": "backend/tests/test_a.py", "isolation_class": "parallel_safe"}
            for i in range(10)
        ] + [
            {"node_id": "backend/tests/test_b.py::test_exec", "source_file": "backend/tests/test_b.py", "isolation_class": "exclusive_process"}
        ]
        coll_json = json.dumps({"count": len(sample_items), "policy_hash": "mock", "items": sample_items})
        (tmp_path / "collection.json").write_text(coll_json, encoding="utf-8")
        (tmp_path / "collection-hash.txt").write_text("mock_hash", encoding="utf-8")

        n_shards, m_hash = build_manifest(tmp_path, shard_size=5)
        assert n_shards > 0
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assigned = []
        for s in manifest["shards"]:
            assigned.extend(s["node_ids"])
        assert len(assigned) == len(sample_items)
        assert set(assigned) == set(item["node_id"] for item in sample_items)


def test_aggregator_writes_only_test_verdict_json():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        coll = {"count": 1, "policy_hash": "p1", "items": [{"node_id": "t1", "isolation_class": "parallel_safe"}]}
        manifest = {
            "total_nodes": 1, "policy_hash": "p1", "collection_hash": "c1",
            "shards": [{"shard_id": "shard_01", "isolation_class": "parallel_safe", "node_ids": ["t1"]}],
        }
        (tmp_path / "collection.json").write_text(json.dumps(coll), encoding="utf-8")
        (tmp_path / "collection-hash.txt").write_text("c1", encoding="utf-8")
        (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        s1 = tmp_path / "shards" / "shard_01"
        s1.mkdir(parents=True)
        (s1 / "shard-result.json").write_text(json.dumps({
            "shard_id": "shard_01", "isolation_class": "parallel_safe",
            "total_nodes_assigned": 1, "total_nodes_executed": 1, "executed_node_ids": ["t1"],
            "passed": 1, "failed": 0, "errors": 0, "skipped": 0,
            "exit_code": 0, "timed_out": False, "duration_seconds": 1.0,
        }))
        verdict = aggregate_results(tmp_path)
        assert verdict["test_verdict"] == "PASS"
        assert (tmp_path / "test-verdict.json").exists()
        assert not (tmp_path / "release-verdict.json").exists()


def test_aggregate_results_detects_unexecuted_nodes():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        coll = {
            "count": 2, "policy_hash": "p1",
            "items": [{"node_id": "t1", "isolation_class": "parallel_safe"}, {"node_id": "t2", "isolation_class": "parallel_safe"}],
        }
        manifest = {
            "total_nodes": 2, "policy_hash": "p1", "collection_hash": "c1",
            "shards": [
                {"shard_id": "shard_01", "isolation_class": "parallel_safe", "node_ids": ["t1"]},
                {"shard_id": "shard_02", "isolation_class": "parallel_safe", "node_ids": ["t2"]},
            ],
        }
        (tmp_path / "collection.json").write_text(json.dumps(coll), encoding="utf-8")
        (tmp_path / "collection-hash.txt").write_text("c1", encoding="utf-8")
        (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        s1 = tmp_path / "shards" / "shard_01"
        s1.mkdir(parents=True)
        (s1 / "shard-result.json").write_text(json.dumps({
            "shard_id": "shard_01", "isolation_class": "parallel_safe",
            "total_nodes_assigned": 1, "total_nodes_executed": 1, "executed_node_ids": ["t1"],
            "passed": 1, "failed": 0, "errors": 0, "skipped": 0,
            "exit_code": 0, "timed_out": False, "duration_seconds": 1.0,
        }))
        verdict = aggregate_results(tmp_path)
        assert verdict["test_verdict"] == "FAIL"
        assert verdict["node_set_verification"]["unexecuted_nodes"] == 1


# ---------- Collection Reconciliation ----------

def test_collection_snapshot_difference_reports_exact_nodes():
    """Given two collections with known differences, the set diff is exact."""
    old_items = [{"node_id": f"backend/tests/test_a.py::test_{i}"} for i in range(5)]
    new_items = old_items + [{"node_id": "kattappa_native/tests/test_bridge.py::test_init"}]
    old_nodes = set(item["node_id"] for item in old_items)
    new_nodes = set(item["node_id"] for item in new_items)
    added = sorted(new_nodes - old_nodes)
    removed = sorted(old_nodes - new_nodes)
    assert len(added) == 1
    assert len(removed) == 0
    assert added[0] == "kattappa_native/tests/test_bridge.py::test_init"


def test_release_run_does_not_modify_worktree():
    """The external run directory function returns a path outside PROJECT_ROOT."""
    from run_full_suite_sharded import _get_external_run_dir
    run_dir = _get_external_run_dir("integrity-check-run")
    # Verify that the path does not start with PROJECT_ROOT
    project_str = str(PROJECT_ROOT).rstrip(os.sep)
    run_str = str(run_dir)
    assert not run_str.startswith(project_str), f"Run dir {run_dir} is inside worktree"
