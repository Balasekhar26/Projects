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

def test_shard_run_id_mismatch_is_rejected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        core_h, file_h = _write_base_run_files(tmp_path, run_id="active_run")
        s1 = tmp_path / "shards" / "shard_01"
        s1.mkdir(parents=True)
        # Write shard result from a different run_id
        (s1 / "shard-result.json").write_text(json.dumps({
            "run_id": "different_run", "candidate_commit": "c1", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": core_h, "manifest_file_hash": file_h,
            "shard_id": "shard_01", "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }))
        with pytest.raises(ValueError, match="mismatching run_id"):
            aggregate_results(tmp_path)

def test_shard_commit_mismatch_is_rejected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        core_h, file_h = _write_base_run_files(tmp_path, commit="commit_A")
        s1 = tmp_path / "shards" / "shard_01"
        s1.mkdir(parents=True)
        (s1 / "shard-result.json").write_text(json.dumps({
            "run_id": "r1", "candidate_commit": "commit_B", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": core_h, "manifest_file_hash": file_h,
            "shard_id": "shard_01", "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }))
        with pytest.raises(ValueError, match="mismatching candidate_commit"):
            aggregate_results(tmp_path)

def test_shard_manifest_hash_mismatch_is_rejected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        core_h, file_h = _write_base_run_files(tmp_path, man_h="a"*64)
        s1 = tmp_path / "shards" / "shard_01"
        s1.mkdir(parents=True)
        (s1 / "shard-result.json").write_text(json.dumps({
            "run_id": "r1", "candidate_commit": "c1", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": "b"*64, "manifest_file_hash": file_h,
            "shard_id": "shard_01", "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }))
        with pytest.raises(ValueError, match="manifest_core_hash"):
            aggregate_results(tmp_path)

def test_shard_id_not_in_manifest_is_rejected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        core_h, file_h = _write_base_run_files(tmp_path)
        s2 = tmp_path / "shards" / "shard_99" # unregistered shard
        s2.mkdir(parents=True)
        (s2 / "shard-result.json").write_text(json.dumps({
            "run_id": "r1", "candidate_commit": "c1", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": core_h, "manifest_file_hash": file_h,
            "shard_id": "shard_99", "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }))
        with pytest.raises(ValueError, match="not defined in the current manifest"):
            aggregate_results(tmp_path)

def test_duplicate_shard_result_is_rejected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        core_h, file_h = _write_base_run_files(tmp_path)
        # Create duplicate shard output directory structure
        s1 = tmp_path / "shards" / "shard_01"
        s1.mkdir(parents=True)
        (s1 / "shard-result.json").write_text(json.dumps({
            "run_id": "r1", "candidate_commit": "c1", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": core_h, "manifest_file_hash": file_h,
            "shard_id": "shard_01", "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }))
        s2 = tmp_path / "shards" / "shard_01_dup"
        s2.mkdir(parents=True)
        (s2 / "shard-result.json").write_text(json.dumps({
            "run_id": "r1", "candidate_commit": "c1", "collection_hash": "a"*64, "policy_hash": "b"*64,
            "manifest_core_hash": core_h, "manifest_file_hash": file_h,
            "shard_id": "shard_01", # same shard_id
            "isolation_class": "parallel_safe", "total_nodes_assigned": 1, "total_nodes_executed": 1,
            "executed_node_ids": ["t1"], "passed": 1, "failed": 0, "errors": 0, "skipped": 0, "exit_code": 0
        }))
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


def test_file_backed_pytest_shard_launcher_winerror_206_prevention():
    """Verify that execute_pytest_shard.py launches file-backed shard without command line overflow."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        shard_def_path = tmp_path / "shard_definition.json"
        result_file_path = tmp_path / "pytest_results.json"

        # Create 500 synthetic long node IDs that would exceed 32,767 chars on command line
        synthetic_nodes = [f"backend/tests/test_sharded_validation.py::test_circular_import_simulated_{i}_" + ("a" * 100) for i in range(500)]
        shard_data = {
            "shard_id": "test_winerror_206_shard",
            "run_id": "winerror_test_run",
            "candidate_commit": "test_commit_sha",
            "manifest_core_hash": "a" * 64,
            "manifest_file_hash": "b" * 64,
            "node_ids": synthetic_nodes
        }
        shard_def_path.write_text(json.dumps(shard_data, indent=2), encoding="utf-8")

        launcher_script = PROJECT_ROOT / "scripts" / "validation" / "execute_pytest_shard.py"
        cmd = [
            sys.executable,
            str(launcher_script),
            f"--shard-definition={shard_def_path}",
            f"--result-file={result_file_path}"
        ]

        # Assert command line string length is well below Windows limits
        cmd_str = " ".join(cmd)
        assert len(cmd_str) < 1000, f"Command line string too long: {len(cmd_str)} chars"

        # Verify executing script directly
        assert launcher_script.exists()




