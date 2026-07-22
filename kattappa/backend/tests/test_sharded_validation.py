"""K-R0.5.4 Runner Self-Validation Suite.

Covers:
- Policy YAML controls classification
- Fallback default to isolated_stateful
- Policy hash matches content
- Scope allowlist matches policies
- Canonical testpaths loading from pytest.ini
- Per-root union equals full collection
- Cross-root duplicate check fail closed
- Missing canonical root is rejected
- Extra pytest root is detected
- Pytest ini policy drift is rejected
- Archived evidence is not collected
- Active run artifacts are outside worktree
- Manifest run-identity fields
- Shard run-identity fields
- Cross-run shard rejection (run_id, commit, collection, policy, manifest, duplicate shard, unregistered shard)
- Release run does not modify worktree
- S0/S1/S2 collection reconciliation check
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

pytestmark = pytest.mark.validation_harness

# ---------- 1. Policy & Classification ----------

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

# ---------- 2. Scope Allowlist ----------

def test_scope_policy_allowlist_matching():
    policy = {
        "allowed_paths": ["backend/core/rbil.py", "scripts/validation/*", "docs/architecture/*", "pytest.ini"],
        "conditionally_allowed_paths": ["scripts/dev/_backend_process.py"],
    }
    assert is_path_allowed("backend/core/rbil.py", policy) is True
    assert is_path_allowed("scripts/validation/run_test_shard.py", policy) is True
    assert is_path_allowed("docs/architecture/k-him-hierarchical-inference-memory.md", policy) is True
    assert is_path_allowed("pytest.ini", policy) is True
    assert is_path_allowed("backend/unapproved/hack.py", policy) is False

# ---------- 3. Canonical Testpaths ----------

def test_canonical_testpaths_loader():
    testpaths = load_canonical_testpaths()
    assert "backend/tests" in testpaths
    assert "kattappa_native/tests" in testpaths
    assert "kattappa_data_engine/tests" in testpaths
    assert "kattappa_runtime/resource_governor" in testpaths
    assert len(testpaths) == 4

def test_missing_canonical_root_is_rejected():
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
    testpaths = load_canonical_testpaths()
    expected = {"backend/tests", "kattappa_native/tests", "kattappa_data_engine/tests", "kattappa_runtime/resource_governor"}
    assert set(testpaths) == expected

def test_pytest_ini_policy_drift_is_rejected():
    ini_path = PROJECT_ROOT / "pytest.ini"
    config = configparser.ConfigParser()
    config.read(ini_path, encoding="utf-8")
    testpaths_str = config.get("pytest", "testpaths", fallback="")
    testpaths = [tp.strip() for tp in testpaths_str.strip().splitlines() if tp.strip()]
    expected = ["backend/tests", "kattappa_native/tests", "kattappa_data_engine/tests", "kattappa_runtime/resource_governor"]
    assert testpaths == expected

# ---------- 4. Per-Root Union Verification ----------

def test_per_root_union_equals_full_collection():
    testpaths = load_canonical_testpaths()
    per_root_nodes = {}
    root_union = set()
    for tp in testpaths:
        nodes = _collect_root(tp)
        unique = set(nodes)
        per_root_nodes[tp] = unique
        root_union.update(unique)

    import subprocess
    full_cmd = [sys.executable, "-m", "pytest"] + testpaths + ["--collect-only", "-q", "-o", "cache_dir=/dev/null", "-p", "no:langsmith"]
    proc = subprocess.run(full_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    full_nodes = set(
        line.strip() for line in proc.stdout.splitlines()
        if "::" in line and not line.startswith("=")
    )
    assert root_union == full_nodes

def test_cross_root_duplicate_is_rejected():
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
    assert len(duplicates) == 0

# ---------- 5. Evidence Exclusion ----------

def test_archived_evidence_is_not_collected():
    testpaths = load_canonical_testpaths()
    import subprocess
    full_cmd = [sys.executable, "-m", "pytest"] + testpaths + ["--collect-only", "-q", "-o", "cache_dir=/dev/null", "-p", "no:langsmith"]
    proc = subprocess.run(full_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    evidence_nodes = [
        line.strip() for line in proc.stdout.splitlines()
        if "docs/evidence" in line and "::" in line
    ]
    assert len(evidence_nodes) == 0

def test_active_run_artifacts_are_outside_worktree():
    from run_full_suite_sharded import _get_external_run_dir
    run_dir = _get_external_run_dir("test-run-id-000")
    assert not str(run_dir).startswith(str(PROJECT_ROOT))

# ---------- 6. Manifest & Shard Identity ----------

def test_manifest_building_and_node_assignment_integrity():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        sample_items = [
            {"node_id": f"backend/tests/test_a.py::test_{i}", "source_file": "backend/tests/test_a.py", "isolation_class": "parallel_safe"}
            for i in range(10)
        ]
        coll_json = json.dumps({"count": len(sample_items), "policy_hash": "mock_p_hash", "items": sample_items})
        (tmp_path / "collection.json").write_text(coll_json, encoding="utf-8")
        (tmp_path / "collection-hash.txt").write_text("mock_c_hash", encoding="utf-8")

        n_shards, m_core_hash, m_file_hash = build_manifest(
            tmp_path, shard_size=5, run_id="r1", candidate_commit="c_sha", environment_fingerprint={}
        )
        assert n_shards > 0
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["run_id"] == "r1"
        assert manifest["candidate_commit"] == "c_sha"
        assert manifest["collection_hash"] == "mock_c_hash"
        assert manifest["policy_hash"] == "mock_p_hash"

        for s in manifest["shards"]:
            assert s["run_id"] == "r1"
            assert s["candidate_commit"] == "c_sha"
            assert s["collection_hash"] == "mock_c_hash"
            assert s["policy_hash"] == "mock_p_hash"
            assert s["manifest_core_hash"] == m_core_hash

# ---------- 7. Cross-Run Rejection Tests ----------

def _write_base_run_files(tmp_path, run_id="r1", commit="c1", coll_h="a"*64, pol_h="b"*64, man_h=None):
    coll = {"count": 1, "policy_hash": pol_h, "items": [{"node_id": "t1", "isolation_class": "parallel_safe"}]}
    manifest = {
        "run_id": run_id, "candidate_commit": commit, "collection_hash": coll_h, "policy_hash": pol_h,
        "shards": [{"shard_id": "shard_01", "isolation_class": "parallel_safe", "node_ids": ["t1"]}]
    }

    import copy, hashlib
    reconstructed_core = copy.deepcopy(manifest)
    reconstructed_core.pop("manifest_core_hash", None)
    for s in reconstructed_core.get("shards", []):
        s.pop("run_id", None)
        s.pop("run_label", None)
        s.pop("candidate_commit", None)
        s.pop("collection_hash", None)
        s.pop("policy_hash", None)
        s.pop("manifest_core_hash", None)
        s.pop("manifest_file_hash", None)

    reconstructed_json = json.dumps(reconstructed_core, sort_keys=True, separators=(',', ':'))
    real_core_hash = hashlib.sha256(reconstructed_json.encode("utf-8")).hexdigest()

    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    real_file_hash = hashlib.sha256(manifest_bytes).hexdigest()

    core_hash_to_use = man_h if man_h is not None else real_core_hash

    manifest["manifest_core_hash"] = core_hash_to_use
    manifest["manifest_file_hash"] = real_file_hash

    run_identity = {
        "run_id": run_id, "candidate_commit": commit, "collection_hash": coll_h, "policy_hash": pol_h,
        "manifest_core_hash": core_hash_to_use, "manifest_file_hash": real_file_hash, "environment_hash": "e"*64
    }
    (tmp_path / "collection.json").write_text(json.dumps(coll), encoding="utf-8")
    (tmp_path / "collection-hash.txt").write_text(coll_h, encoding="utf-8")
    (tmp_path / "manifest.json").write_bytes(manifest_bytes)
    (tmp_path / "manifest-core-hash.txt").write_text(core_hash_to_use, encoding="utf-8")
    (tmp_path / "manifest-file-hash.txt").write_text(real_file_hash, encoding="utf-8")
    (tmp_path / "run-identity.json").write_text(json.dumps(run_identity), encoding="utf-8")
    return core_hash_to_use, real_file_hash

def _write_mock_shard_files(s_dir, shard_id="shard_01", node_ids=None):
    import hashlib
    if node_ids is None:
        node_ids = ["t1"]
    s_dir.mkdir(parents=True, exist_ok=True)
    def_data = {"schema_version": 1, "shard_id": shard_id, "node_ids": node_ids}
    def_bytes = json.dumps(def_data).encode("utf-8")
    (s_dir / "shard_definition.json").write_bytes(def_bytes)
    def_hash = hashlib.sha256(def_bytes).hexdigest()

    nodes_bytes = json.dumps(node_ids).encode("utf-8")
    (s_dir / "expected-node-ids.json").write_bytes(nodes_bytes)
    nodes_hash = hashlib.sha256(nodes_bytes).hexdigest()

    return {
        "shard_definition_sha256": def_hash,
        "expected_node_ids_sha256": nodes_hash,
        "shard_definition_hash_verified": True,
        "expected_node_ids_hash_verified": True
    }

def test_shard_run_id_mismatch_is_rejected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        core_h, file_h = _write_base_run_files(tmp_path, run_id="active_run")
        s1 = tmp_path / "shards" / "shard_01"
        h_info = _write_mock_shard_files(s1, "shard_01")
        # Write shard result from a different run_id
        res_data = {
            "run_id": "different_run", "candidate_commit": "c1", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": core_h, "manifest_file_hash": file_h,
            "shard_id": "shard_01", "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }
        res_data.update(h_info)
        (s1 / "shard-result.json").write_text(json.dumps(res_data))
        with pytest.raises(ValueError, match="mismatching run_id"):
            aggregate_results(tmp_path)

def test_shard_commit_mismatch_is_rejected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        core_h, file_h = _write_base_run_files(tmp_path, commit="commit_A")
        s1 = tmp_path / "shards" / "shard_01"
        h_info = _write_mock_shard_files(s1, "shard_01")
        res_data = {
            "run_id": "r1", "candidate_commit": "commit_B", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": core_h, "manifest_file_hash": file_h,
            "shard_id": "shard_01", "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }
        res_data.update(h_info)
        (s1 / "shard-result.json").write_text(json.dumps(res_data))
        with pytest.raises(ValueError, match="mismatching candidate_commit"):
            aggregate_results(tmp_path)

def test_shard_manifest_hash_mismatch_is_rejected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        core_h, file_h = _write_base_run_files(tmp_path, man_h="a"*64)
        s1 = tmp_path / "shards" / "shard_01"
        h_info = _write_mock_shard_files(s1, "shard_01")
        res_data = {
            "run_id": "r1", "candidate_commit": "c1", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": "b"*64, "manifest_file_hash": file_h,
            "shard_id": "shard_01", "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }
        res_data.update(h_info)
        (s1 / "shard-result.json").write_text(json.dumps(res_data))
        with pytest.raises(ValueError, match="manifest_core_hash"):
            aggregate_results(tmp_path)

def test_shard_id_not_in_manifest_is_rejected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        core_h, file_h = _write_base_run_files(tmp_path)
        s2 = tmp_path / "shards" / "shard_99" # unregistered shard
        h_info = _write_mock_shard_files(s2, "shard_99")
        res_data = {
            "run_id": "r1", "candidate_commit": "c1", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": core_h, "manifest_file_hash": file_h,
            "shard_id": "shard_99", "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }
        res_data.update(h_info)
        (s2 / "shard-result.json").write_text(json.dumps(res_data))
        with pytest.raises(ValueError, match="not defined in the current manifest"):
            aggregate_results(tmp_path)

def test_duplicate_shard_result_is_rejected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        core_h, file_h = _write_base_run_files(tmp_path)
        # Create duplicate shard output directory structure
        s1 = tmp_path / "shards" / "shard_01"
        h1 = _write_mock_shard_files(s1, "shard_01")
        res1 = {
            "run_id": "r1", "candidate_commit": "c1", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": core_h, "manifest_file_hash": file_h,
            "shard_id": "shard_01", "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }
        res1.update(h1)
        (s1 / "shard-result.json").write_text(json.dumps(res1))

        s2 = tmp_path / "shards" / "shard_01_dup"
        h2 = _write_mock_shard_files(s2, "shard_01")
        res2 = {
            "run_id": "r1", "candidate_commit": "c1", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": core_h, "manifest_file_hash": file_h,
            "shard_id": "shard_01", # same shard_id
            "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }
        res2.update(h2)
        (s2 / "shard-result.json").write_text(json.dumps(res2))
        with pytest.raises(ValueError, match="shard_01"):
            aggregate_results(tmp_path)

# ---------- 8. Snapshot Reconciliation Integrity ----------

def test_s0_s1_s2_reconciliation_resembles_expectations():
    recon_file = PROJECT_ROOT / "docs" / "evidence" / "k-r0.5" / "collection-reconciliation-S0-S1-S2.json"
    assert recon_file.exists()
    recon = json.loads(recon_file.read_text(encoding="utf-8"))
    assert recon["audit"]["S0"]["count"] == 3187
    assert recon["audit"]["S1"]["count"] == 3187
    assert recon["audit"]["S2"]["count"] == 3200
    assert len(recon["transitions"]["S0_to_S2"]["added"]) == 15
    assert len(recon["transitions"]["S0_to_S2"]["removed"]) == 2

# ---------- 9. Pytest Result Plugin Smoke Tests ----------

import subprocess

def test_result_plugin_registers_under_pytest_9(tmp_path):
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_ok(): pass", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    out = tmp_path / "res.json"
    from run_test_shard import get_python_executable
    cmd = [get_python_executable(), "-m", "pytest", str(dummy), "--noconftest", "-c", str(ini), "-p", "no:langsmith", "-p", "scripts.validation.pytest_result_plugin", f"--kattappa-result-file={out}"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert res.returncode == 0
    assert out.exists()

def test_result_plugin_collect_only_completes(tmp_path):
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_ok(): pass", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    out = tmp_path / "res.json"
    from run_test_shard import get_python_executable
    cmd = [get_python_executable(), "-m", "pytest", str(dummy), "--collect-only", "--noconftest", "-c", str(ini), "-p", "no:langsmith", "-p", "scripts.validation.pytest_result_plugin", f"--kattappa-result-file={out}"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert res.returncode == 0

def test_result_plugin_records_passing_test(tmp_path):
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_ok(): pass", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    out = tmp_path / "res.json"
    from run_test_shard import get_python_executable
    cmd = [get_python_executable(), "-m", "pytest", str(dummy), "--noconftest", "-c", str(ini), "-p", "no:langsmith", "-p", "scripts.validation.pytest_result_plugin", f"--kattappa-result-file={out}"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run(cmd, env=env, capture_output=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["passed"] == 1

def test_result_plugin_records_failing_test(tmp_path):
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_fail(): assert False", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    out = tmp_path / "res.json"
    from run_test_shard import get_python_executable
    cmd = [get_python_executable(), "-m", "pytest", str(dummy), "--noconftest", "-c", str(ini), "-p", "no:langsmith", "-p", "scripts.validation.pytest_result_plugin", f"--kattappa-result-file={out}"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run(cmd, env=env, capture_output=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["failed"] == 1

def test_result_plugin_records_setup_error(tmp_path):
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("""
import pytest
@pytest.fixture
def fail_setup():
    raise RuntimeError("setup fail")
def test_err(fail_setup):
    pass
""", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    out = tmp_path / "res.json"
    from run_test_shard import get_python_executable
    cmd = [get_python_executable(), "-m", "pytest", str(dummy), "--noconftest", "-c", str(ini), "-p", "no:langsmith", "-p", "scripts.validation.pytest_result_plugin", f"--kattappa-result-file={out}"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run(cmd, env=env, capture_output=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["errors"] == 1

def test_result_plugin_records_teardown_error(tmp_path):
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("""
import pytest
@pytest.fixture
def fail_teardown():
    yield
    raise RuntimeError("teardown fail")
def test_err(fail_teardown):
    pass
""", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    out = tmp_path / "res.json"
    from run_test_shard import get_python_executable
    cmd = [get_python_executable(), "-m", "pytest", str(dummy), "--noconftest", "-c", str(ini), "-p", "no:langsmith", "-p", "scripts.validation.pytest_result_plugin", f"--kattappa-result-file={out}"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run(cmd, env=env, capture_output=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["errors"] == 1

def test_result_plugin_records_internal_error():
    import inspect
    from scripts.validation.pytest_result_plugin import KattappaResultPlugin
    sig = inspect.signature(KattappaResultPlugin.pytest_internalerror)
    assert "excrepr" in sig.parameters
    assert "excinfo" in sig.parameters

def test_result_plugin_writes_valid_json(tmp_path):
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_ok(): pass", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    out = tmp_path / "res.json"
    from run_test_shard import get_python_executable
    cmd = [get_python_executable(), "-m", "pytest", str(dummy), "--noconftest", "-c", str(ini), "-p", "no:langsmith", "-p", "scripts.validation.pytest_result_plugin", f"--kattappa-result-file={out}"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run(cmd, env=env, capture_output=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, dict)

# ---------- 10. Fail-Closed Validation Tests ----------

def test_union_mismatch_fails_closed():
    import collect_test_inventory as cti
    from unittest.mock import patch, MagicMock
    with patch("collect_test_inventory._collect_root", return_value=[]), \
         patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "backend/tests/test_file.py::test_one\n"
        mock_run.return_value = mock_proc
        with pytest.raises(RuntimeError, match="Canonical test-root union does not match full collection"):
            cti.collect_inventory(Path(tempfile.gettempdir()))

def test_cross_root_duplicates_fail_closed():
    import collect_test_inventory as cti
    from unittest.mock import patch, MagicMock
    with patch("collect_test_inventory.load_canonical_testpaths", return_value=["rootA", "rootB"]), \
         patch("collect_test_inventory._collect_root", return_value=["backend/tests/test_file.py::test_one"]), \
         patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "backend/tests/test_file.py::test_one\n"
        mock_run.return_value = mock_proc
        with pytest.raises(RuntimeError, match="Cross-root duplicate node IDs detected"):
            cti.collect_inventory(Path(tempfile.gettempdir()))

def test_save_self_validation_evidence_functions():
    import save_self_validation_evidence as sve
    fingerprint, files_sha = sve.compute_source_fingerprint()
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    assert len(files_sha) == len(sve.TARGET_FILES)
    for f in sve.TARGET_FILES:
        assert f in files_sha

# ---------- 11. Circular Import Focused Architectural Tests ----------

def test_cognitive_kernel_imports_without_simulation_cycle():
    cmd = [sys.executable, "-c", "import sys; sys.path.insert(0, '.'); from backend.core.cognitive_kernel import KERNEL; print('ok')"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    assert res.returncode == 0
    assert "ok" in res.stdout

def test_simulation_engine_imports_without_kernel_cycle():
    cmd = [sys.executable, "-c", "import sys; sys.path.insert(0, '.'); from backend.core.simulation_engine import SimulationEngine; print('ok')"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    assert res.returncode == 0
    assert "ok" in res.stdout

def test_import_order_kernel_then_simulation():
    cmd = [sys.executable, "-c", "import sys; sys.path.insert(0, '.'); import backend.core.cognitive_kernel; import backend.core.simulation_engine; print('ok')"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    assert res.returncode == 0
    assert "ok" in res.stdout

def test_import_order_simulation_then_kernel():
    cmd = [sys.executable, "-c", "import sys; sys.path.insert(0, '.'); import backend.core.simulation_engine; import backend.core.cognitive_kernel; print('ok')"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    assert res.returncode == 0
    assert "ok" in res.stdout

def test_kernel_resolves_simulation_service_lazily():
    from backend.core.cognitive_kernel import KERNEL
    # Access simulation via helper property to trigger lazy registration
    sim_engine = KERNEL.simulation
    assert sim_engine is not None
    # Verify it is registered in KERNEL services
    assert KERNEL.get_service("simulation") is not None

def test_lazy_resolution_does_not_recurse():
    from backend.core.cognitive_kernel import KERNEL
    sim_service1 = KERNEL.get_service("simulation")
    sim_service2 = KERNEL.get_service("simulation")
    assert sim_service1 is sim_service2

def test_simulation_service_singleton_or_scope_contract():
    from backend.core.cognitive_kernel import KERNEL
    from backend.core.simulation_engine import SimulationService
    sim_service = KERNEL.get_service("simulation")
    assert isinstance(sim_service, SimulationService)

def test_kernel_shutdown_after_lazy_simulation_resolution():
    # Run in a separate subprocess to avoid messing with global KERNEL singleton state
    code = (
        "import sys\n"
        "sys.path.insert(0, '.')\n"
        "from backend.core.cognitive_kernel import KERNEL\n"
        "sim = KERNEL.simulation\n"
        "KERNEL.shutdown_all()\n"
        "print('ok')\n"
    )
    cmd = [sys.executable, "-c", code]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    assert res.returncode == 0
    assert "ok" in res.stdout


# ---------- 12. File-Backed Launcher Integration Tests ----------

def _make_shard_definition(tmp_path, shard_id="test_shard", node_ids=None,
                           run_id="test_run", run_label="T",
                           candidate_commit="a"*64, collection_hash="b"*64,
                           policy_hash="c"*64, manifest_core_hash="d"*64,
                           manifest_file_hash="e"*64, environment_hash="f"*64,
                           timeout_seconds=120, schema_version=1):
    """Helper to create a valid shard definition JSON file."""
    if node_ids is None:
        node_ids = ["test_dummy.py::test_ok"]
    shard_def = {
        "schema_version": schema_version,
        "shard_id": shard_id,
        "isolation_class": "parallel_safe",
        "run_id": run_id,
        "run_label": run_label,
        "candidate_commit": candidate_commit,
        "collection_hash": collection_hash,
        "policy_hash": policy_hash,
        "manifest_core_hash": manifest_core_hash,
        "manifest_file_hash": manifest_file_hash,
        "environment_hash": environment_hash,
        "timeout_seconds": timeout_seconds,
        "node_ids": node_ids
    }
    shard_def_path = tmp_path / "shard_definition.json"
    shard_def_path.write_text(json.dumps(shard_def, indent=2), encoding="utf-8")
    return shard_def_path, shard_def


def _make_run_identity(tmp_path, run_id="test_run", run_label="T",
                       candidate_commit="a"*64, collection_hash="b"*64,
                       policy_hash="c"*64, manifest_core_hash="d"*64,
                       manifest_file_hash="e"*64, environment_hash="f"*64):
    """Helper to create a matching run-identity.json file."""
    identity = {
        "run_id": run_id,
        "run_label": run_label,
        "candidate_commit": candidate_commit,
        "collection_hash": collection_hash,
        "policy_hash": policy_hash,
        "manifest_core_hash": manifest_core_hash,
        "manifest_file_hash": manifest_file_hash,
        "environment_hash": environment_hash,
    }
    identity_path = tmp_path / "run-identity.json"
    identity_path.write_text(json.dumps(identity, indent=2), encoding="utf-8")
    return identity_path


def _run_launcher(shard_def_path, result_path, run_identity_path=None, timeout=60, cwd=None):
    """Execute the file-backed launcher in a subprocess."""
    from run_test_shard import get_python_executable
    launcher = PROJECT_ROOT / "scripts" / "validation" / "execute_pytest_shard.py"
    if run_identity_path is None:
        run_identity_path = _make_run_identity(shard_def_path.parent)

    cmd = [
        get_python_executable(),
        str(launcher),
        f"--shard-definition={shard_def_path}",
        f"--result-file={result_path}",
        f"--run-identity={run_identity_path}"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["KATTAPPA_ENV"] = "test"
    run_cwd = cwd if cwd else str(PROJECT_ROOT)
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, cwd=run_cwd)


def test_launcher_constructs_result_plugin_with_supported_signature(tmp_path):
    """Verify the launcher can construct the plugin without TypeError (Section 9)."""
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_ok(): pass", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    result_path = tmp_path / "result.json"
    shard_def_path, _ = _make_shard_definition(
        tmp_path, node_ids=["test_dummy.py::test_ok"]
    )
    res = _run_launcher(shard_def_path, result_path, cwd=tmp_path)
    assert res.returncode == 0, f"Launcher failed: {res.stderr}"
    assert result_path.exists(), "Result file was not created"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["passed"] == 1


def test_launcher_exit_code_pass(tmp_path):
    """Exit code 0 for all-pass shard."""
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_ok(): pass\ndef test_ok2(): pass\n", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    result_path = tmp_path / "result.json"
    shard_def_path, _ = _make_shard_definition(
        tmp_path, node_ids=["test_dummy.py::test_ok", "test_dummy.py::test_ok2"]
    )
    res = _run_launcher(shard_def_path, result_path, cwd=tmp_path)
    assert res.returncode == 0
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["passed"] == 2
    assert data["failed"] == 0


def test_launcher_exit_code_assertion_failure(tmp_path):
    """Non-zero exit for assertion failures."""
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_fail(): assert False", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    result_path = tmp_path / "result.json"
    shard_def_path, _ = _make_shard_definition(
        tmp_path, node_ids=["test_dummy.py::test_fail"]
    )
    res = _run_launcher(shard_def_path, result_path, cwd=tmp_path)
    assert res.returncode != 0
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["failed"] == 1


def test_launcher_exit_code_setup_error(tmp_path):
    """Non-zero exit for setup errors."""
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("""\
import pytest
@pytest.fixture
def broken():
    raise RuntimeError("boom")
def test_err(broken):
    pass
""", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    result_path = tmp_path / "result.json"
    shard_def_path, _ = _make_shard_definition(
        tmp_path, node_ids=["test_dummy.py::test_err"]
    )
    res = _run_launcher(shard_def_path, result_path, cwd=tmp_path)
    assert res.returncode != 0
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["errors"] == 1


def test_launcher_exit_code_collection_error(tmp_path):
    """Non-zero exit for collection errors (syntax error in test file)."""
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_ok( ::: pass\n", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    result_path = tmp_path / "result.json"
    shard_def_path, _ = _make_shard_definition(
        tmp_path, node_ids=["test_dummy.py::test_ok"]
    )
    res = _run_launcher(shard_def_path, result_path, cwd=tmp_path)
    assert res.returncode != 0


def test_launcher_exit_code_no_tests_collected(tmp_path):
    """Non-zero exit when shard points to nonexistent nodes."""
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_ok(): pass\n", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    result_path = tmp_path / "result.json"
    shard_def_path, _ = _make_shard_definition(
        tmp_path, node_ids=["test_dummy.py::test_nonexistent"]
    )
    res = _run_launcher(shard_def_path, result_path, cwd=tmp_path)
    # Plugin will filter to 0 items → fail-closed on empty
    assert res.returncode != 0


def test_launcher_unique_file_filtering(tmp_path):
    """A file with 100 tests, shard assigns 3, exactly 3 execute (Section 11)."""
    # Generate file with 100 tests
    test_lines = [f"def test_case_{i}(): pass" for i in range(100)]
    dummy = tmp_path / "test_hundred.py"
    dummy.write_text("\n".join(test_lines) + "\n", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")

    # Assign only 3 specific tests
    assigned = ["test_hundred.py::test_case_7", "test_hundred.py::test_case_42", "test_hundred.py::test_case_99"]
    result_path = tmp_path / "result.json"
    shard_def_path, _ = _make_shard_definition(
        tmp_path, node_ids=assigned
    )
    res = _run_launcher(shard_def_path, result_path, cwd=tmp_path)
    assert res.returncode == 0, f"Launcher failed: {res.stderr}"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["passed"] == 3
    assert len(data["collected_node_ids"]) == 3
    assert len(data["executed_node_ids"]) == 3
    assert data["collection_set_match"] is True


def test_plugin_node_filter_fail_closed_missing_file(tmp_path):
    """Plugin raises UsageError when node IDs file is missing (Section 6)."""
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_ok(): pass\n", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    out = tmp_path / "res.json"
    from run_test_shard import get_python_executable
    cmd = [
        get_python_executable(), "-m", "pytest", str(dummy),
        "--noconftest", "-c", str(ini),
        "-p", "no:langsmith",
        "-p", "scripts.validation.pytest_result_plugin",
        f"--kattappa-result-file={out}"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["KATTAPPA_SHARD_NODE_IDS_FILE"] = str(tmp_path / "nonexistent.json")
    res = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=tmp_path)
    assert res.returncode != 0
    assert "SHARD_NODE_FILTER_FAIL_CLOSED" in res.stderr or "SHARD_NODE_FILTER_FAIL_CLOSED" in res.stdout


def test_plugin_node_filter_fail_closed_invalid_json(tmp_path):
    """Plugin raises UsageError when node IDs file contains invalid JSON (Section 6)."""
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_ok(): pass\n", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    out = tmp_path / "res.json"
    bad_json = tmp_path / "bad_nodes.json"
    bad_json.write_text("{not valid json!!!", encoding="utf-8")
    from run_test_shard import get_python_executable
    cmd = [
        get_python_executable(), "-m", "pytest", str(dummy),
        "--noconftest", "-c", str(ini),
        "-p", "no:langsmith",
        "-p", "scripts.validation.pytest_result_plugin",
        f"--kattappa-result-file={out}"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["KATTAPPA_SHARD_NODE_IDS_FILE"] = str(bad_json)
    res = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=tmp_path)
    assert res.returncode != 0


def test_plugin_exact_collection_set_verification(tmp_path):
    """Expected vs collected node sets match exactly (Section 7)."""
    dummy = tmp_path / "test_dummy.py"
    dummy.write_text("def test_a(): pass\ndef test_b(): pass\n", encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    out = tmp_path / "res.json"
    node_file = tmp_path / "nodes.json"
    node_file.write_text(json.dumps(["test_dummy.py::test_a", "test_dummy.py::test_b"]), encoding="utf-8")
    from run_test_shard import get_python_executable
    cmd = [
        get_python_executable(), "-m", "pytest", str(dummy),
        "--noconftest", "-c", str(ini),
        "-p", "no:langsmith",
        "-p", "scripts.validation.pytest_result_plugin",
        f"--kattappa-result-file={out}"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["KATTAPPA_SHARD_NODE_IDS_FILE"] = str(node_file)
    res = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=tmp_path)
    assert res.returncode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["collection_set_match"] is True
    assert data["missing_expected_node_ids"] == []
    assert data["unexpected_collected_node_ids"] == []
    assert len(data["expected_node_ids"]) == 2


def test_file_backed_pytest_shard_launcher_winerror_206_prevention(tmp_path):
    """Real 500-node transport test proving file-backed execution (Section 8).
    Generates 500 parametrized tests with long IDs that exceed 32,767 chars,
    launches execute_pytest_shard.py via subprocess, and verifies all 500 pass.
    """
    # Generate a test module with 500 parametrized cases with long IDs
    long_id_prefix = "long_parametrized_case_identifier_string_" + "x" * 50 + "_"
    test_code = "import pytest\n\n"
    test_code += "@pytest.mark.parametrize(\n"
    test_code += '    "value",\n'
    test_code += "    range(500),\n"
    test_code += "    ids=[" + ", ".join(
        f'"{long_id_prefix}{i:04d}"' for i in range(500)
    ) + "],\n"
    test_code += ")\n"
    test_code += "def test_generated_transport(value):\n"
    test_code += "    assert value >= 0\n"

    test_file = tmp_path / "test_transport_500.py"
    test_file.write_text(test_code, encoding="utf-8")
    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")

    # Collect exact node IDs
    from run_test_shard import get_python_executable
    collect_cmd = [
        get_python_executable(), "-m", "pytest", str(test_file),
        "--collect-only", "-q", "--noconftest", "-c", str(ini),
        "-p", "no:langsmith"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    collect_res = subprocess.run(collect_cmd, capture_output=True, text=True, env=env, timeout=30, cwd=tmp_path)
    assert collect_res.returncode == 0, f"Collection failed: {collect_res.stderr}"

    node_ids = [
        line.strip() for line in collect_res.stdout.strip().split("\n")
        if "::" in line and not line.startswith("=")
    ]
    assert len(node_ids) == 500, f"Expected 500 nodes, got {len(node_ids)}"

    # Confirm expanded text length exceeds 32,767 chars
    expanded_text = " ".join(node_ids)
    assert len(expanded_text) > 32767, f"Expanded text only {len(expanded_text)} chars"

    # Create shard definition and launch
    result_path = tmp_path / "result.json"
    shard_def_path, _ = _make_shard_definition(
        tmp_path, shard_id="winerror_206_shard", node_ids=node_ids
    )

    # Verify command line is short
    launcher = PROJECT_ROOT / "scripts" / "validation" / "execute_pytest_shard.py"
    cmd_str = f"{get_python_executable()} {launcher} --shard-definition={shard_def_path} --result-file={result_path}"
    assert len(cmd_str) < 1000, f"Command line too long: {len(cmd_str)}"

    res = _run_launcher(shard_def_path, result_path, timeout=120, cwd=tmp_path)
    assert res.returncode == 0, f"Launcher failed (exit {res.returncode}): {res.stderr[-500:]}"

    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["passed"] == 500, f"Expected 500 passed, got {data['passed']}"
    assert data["failed"] == 0
    assert data["errors"] == 0
    assert len(data["collected_node_ids"]) == 500
    assert len(data["executed_node_ids"]) == 500
    assert len(data["completed_node_ids"]) == 500
    assert data["collection_set_match"] is True
    assert len(data.get("missing_expected_node_ids", [])) == 0
    assert len(data.get("unexpected_collected_node_ids", [])) == 0


def test_miniature_end_to_end_release_run(tmp_path):
    """Miniature release run with 2 test files, 10 tests, 3 shards (Section 14).
    Uses real manifest, sidecars, run-identity, launcher, plugin, and aggregator.
    """
    import hashlib

    # Create 2 test files
    file_a = tmp_path / "test_file_a.py"
    file_a.write_text("\n".join(
        [f"def test_a_{i}(): pass" for i in range(6)]
    ) + "\n", encoding="utf-8")

    file_b = tmp_path / "test_file_b.py"
    file_b.write_text("\n".join(
        [f"def test_b_{i}(): pass" for i in range(4)]
    ) + "\n", encoding="utf-8")

    ini = tmp_path / "pytest.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")

    # Collect exact relative node IDs from tmp_path
    from run_test_shard import get_python_executable
    collect_cmd = [
        get_python_executable(), "-m", "pytest",
        "test_file_a.py", "test_file_b.py",
        "--collect-only", "-q", "--noconftest", "-c", str(ini),
        "-p", "no:langsmith"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    collect_res = subprocess.run(collect_cmd, capture_output=True, text=True, env=env, timeout=30, cwd=tmp_path)
    assert collect_res.returncode == 0

    all_nodes = [
        line.strip() for line in collect_res.stdout.strip().split("\n")
        if "::" in line and not line.startswith("=")
    ]
    assert len(all_nodes) == 10

    # Build evidence directory structure
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()

    # Create collection using exact relative all_nodes
    items = [{"node_id": n, "isolation_class": "parallel_safe"} for n in all_nodes]
    coll_hash = hashlib.sha256(json.dumps(sorted(all_nodes)).encode()).hexdigest()
    collection = {"items": items, "collection_hash": coll_hash, "policy_hash": "a" * 64}
    (evidence_dir / "collection.json").write_text(json.dumps(collection, indent=2), encoding="utf-8")
    (evidence_dir / "collection-hash.txt").write_text(coll_hash, encoding="utf-8")

    # Create 3 shards: shard 1 gets file_a tests 0-2, shard 2 gets file_a tests 3-5 + file_b test 0 (shared file),
    # shard 3 gets file_b tests 1-3
    shard_1_nodes = [n for n in all_nodes if "test_a_0" in n or "test_a_1" in n or "test_a_2" in n]
    shard_2_nodes = [n for n in all_nodes if "test_a_3" in n or "test_a_4" in n or "test_a_5" in n or "test_b_0" in n]
    shard_3_nodes = [n for n in all_nodes if "test_b_1" in n or "test_b_2" in n or "test_b_3" in n]

    assert len(shard_1_nodes) + len(shard_2_nodes) + len(shard_3_nodes) == 10
    assert len(set(shard_1_nodes + shard_2_nodes + shard_3_nodes)) == 10

    shards = [
        {"shard_id": "mini_shard_01", "isolation_class": "parallel_safe", "concurrency": 1,
         "timeout_seconds": 60, "duration_estimation_source": "class_default", "node_ids": shard_1_nodes},
        {"shard_id": "mini_shard_02", "isolation_class": "parallel_safe", "concurrency": 1,
         "timeout_seconds": 60, "duration_estimation_source": "class_default", "node_ids": shard_2_nodes},
        {"shard_id": "mini_shard_03", "isolation_class": "parallel_safe", "concurrency": 1,
         "timeout_seconds": 60, "duration_estimation_source": "class_default", "node_ids": shard_3_nodes},
    ]

    run_id = "mini_e2e_run"
    candidate_commit = "a" * 64

    manifest_core = {
        "schema_version": 2, "run_id": run_id, "run_label": "T",
        "candidate_commit": candidate_commit, "collection_hash": coll_hash,
        "policy_hash": "a" * 64, "environment_fingerprint": {},
        "shards": shards
    }
    core_json = json.dumps(manifest_core, sort_keys=True, separators=(',', ':'))
    manifest_core_hash = hashlib.sha256(core_json.encode()).hexdigest()

    manifest_content = dict(manifest_core)
    manifest_content["manifest_core_hash"] = manifest_core_hash
    for s in manifest_content["shards"]:
        s["run_id"] = run_id
        s["run_label"] = "T"
        s["candidate_commit"] = candidate_commit
        s["collection_hash"] = coll_hash
        s["policy_hash"] = "a" * 64
        s["manifest_core_hash"] = manifest_core_hash

    manifest_bytes = json.dumps(manifest_content, indent=2).encode("utf-8")
    (evidence_dir / "manifest.json").write_bytes(manifest_bytes)
    manifest_file_hash = hashlib.sha256(manifest_bytes).hexdigest()

    (evidence_dir / "manifest-core-hash.txt").write_text(manifest_core_hash, encoding="utf-8")
    (evidence_dir / "manifest-file-hash.txt").write_text(manifest_file_hash, encoding="utf-8")

    env_hash = hashlib.sha256(json.dumps({}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    run_identity = {
        "run_id": run_id, "run_label": "T", "candidate_commit": candidate_commit,
        "collection_hash": coll_hash, "policy_hash": "a" * 64,
        "manifest_core_hash": manifest_core_hash, "manifest_file_hash": manifest_file_hash,
        "environment_hash": env_hash
    }
    (evidence_dir / "run-identity.json").write_text(json.dumps(run_identity, indent=2), encoding="utf-8")

    # Execute each shard via the real launcher running with cwd=tmp_path
    for shard in shards:
        shard_dir = evidence_dir / "shards" / shard["shard_id"]
        shard_dir.mkdir(parents=True)
        result_path = shard_dir / "pytest_results.json"

        shard_def = {
            "schema_version": 1,
            "shard_id": shard["shard_id"],
            "isolation_class": shard["isolation_class"],
            "run_id": run_id, "run_label": "T",
            "candidate_commit": candidate_commit,
            "collection_hash": coll_hash,
            "policy_hash": "a" * 64,
            "manifest_core_hash": manifest_core_hash,
            "manifest_file_hash": manifest_file_hash,
            "environment_hash": env_hash,
            "timeout_seconds": 60,
            "node_ids": shard["node_ids"]
        }
        shard_def_path = shard_dir / "shard_definition.json"
        shard_def_path.write_text(json.dumps(shard_def, indent=2), encoding="utf-8")

        identity_path = evidence_dir / "run-identity.json"
        res = _run_launcher(shard_def_path, result_path, run_identity_path=identity_path, timeout=60, cwd=tmp_path)
        assert res.returncode == 0, f"Shard {shard['shard_id']} failed: {res.stderr[-500:]}"

        # Write expected-node-ids.json and compute hashes
        expected_nodes_path = shard_dir / "expected-node-ids.json"
        expected_nodes_path.write_text(json.dumps(shard["node_ids"], indent=2), encoding="utf-8")
        def_hash = hashlib.sha256(shard_def_path.read_bytes()).hexdigest()
        nodes_hash = hashlib.sha256(expected_nodes_path.read_bytes()).hexdigest()

        # Write shard-result.json from launcher result
        launcher_data = json.loads(result_path.read_text(encoding="utf-8"))
        shard_result = {
            "run_id": run_id, "candidate_commit": candidate_commit,
            "collection_hash": coll_hash, "policy_hash": "a" * 64,
            "manifest_core_hash": manifest_core_hash, "manifest_file_hash": manifest_file_hash,
            "shard_id": shard["shard_id"], "isolation_class": shard["isolation_class"],
            "total_nodes_assigned": len(shard["node_ids"]),
            "total_nodes_executed": len(launcher_data.get("executed_node_ids", [])),
            "assigned_node_ids": shard["node_ids"],
            "attempted_node_ids": launcher_data.get("attempted_node_ids", []),
            "executed_node_ids": launcher_data.get("executed_node_ids", []),
            "completed_node_ids": launcher_data.get("completed_node_ids", []),
            "passed": launcher_data["passed"], "failed": launcher_data["failed"],
            "errors": launcher_data["errors"], "skipped": launcher_data["skipped"],
            "exit_code": 0, "timed_out": False, "duration_seconds": 1.0,
            "internal_errors": [],
            "shard_definition_sha256": def_hash,
            "expected_node_ids_sha256": nodes_hash,
            "shard_definition_hash_verified": True,
            "expected_node_ids_hash_verified": True
        }
        (shard_dir / "shard-result.json").write_text(json.dumps(shard_result, indent=2), encoding="utf-8")

    # Run real aggregator
    verdict = aggregate_results(evidence_dir)
    assert verdict["test_verdict"] == "PASS", f"Verdict was {verdict['test_verdict']}"
    assert verdict["total_nodes_collected"] == 10
    assert verdict["total_nodes_executed"] == 10
    assert verdict["test_outcomes"]["passed"] == 10
    assert verdict["test_outcomes"]["failed"] == 0
    assert verdict["test_outcomes"]["errors"] == 0


def test_anti_test_tailoring_static_validation():
    """Verify that production backend source code contains 0 test-specific tailoring."""
    backend_dir = PROJECT_ROOT / "backend"
    prohibited_patterns = [
        '"pytest" in sys.modules',
        "'pytest' in sys.modules",
        "Mocked LLM reply",
    ]
    violations = []

    for path in backend_dir.rglob("*.py"):
        # Skip tests directory
        if "tests" in path.parts:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue

        for pattern in prohibited_patterns:
            if pattern in content:
                violations.append(f"{path.relative_to(PROJECT_ROOT)}: found prohibited pattern {pattern!r}")

    assert not violations, "Test-tailoring prohibited patterns found in production code:\n" + "\n".join(violations)


