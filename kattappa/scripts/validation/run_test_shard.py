import sys
import os
import json
import time
import socket
import psutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "validation"))
from collect_test_inventory import load_shard_policy

USED_DATA_ROOTS = set()

def get_busy_ports(ports: list[int] = None) -> set[int]:
    if ports is None:
        ports = [8000, 8080, 8443, 9090]
    busy = set()
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.1)
            try:
                # If we cannot bind, the port is busy
                probe.bind(("127.0.0.1", port))
            except OSError:
                busy.add(port)
    return busy

def get_python_processes() -> set[int]:
    py_procs = set()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = p.info.get("cmdline") or []
            cmd_str = " ".join(cmd).lower()
            if "python" in cmd_str or "pytest" in cmd_str:
                py_procs.add(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return py_procs

def kill_process_tree(pid: int, timeout: float = 10.0) -> tuple[int, list[int], str]:
    surviving_pids = []
    cleanup_log = []
    return_code = 0
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        all_procs = children + [parent]

        if os.name == "nt":
            res = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True)
            return_code = res.returncode
            cleanup_log.append(f"taskkill stdout: {res.stdout.strip()}")
            if res.stderr:
                cleanup_log.append(f"taskkill stderr: {res.stderr.strip()}")
        else:
            for p in all_procs:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass

        gone, alive = psutil.wait_procs(all_procs, timeout=timeout)
        if alive:
            for p in alive:
                surviving_pids.append(p.pid)
                cleanup_log.append(f"Surviving PID detected after cleanup: {p.pid} ({p.name()})")
    except psutil.NoSuchProcess:
        pass
    except Exception as exc:
        cleanup_log.append(f"Process tree cleanup error: {exc}")

    return return_code, surviving_pids, "\n".join(cleanup_log)

def get_python_executable() -> str:
    env_py = os.environ.get("KATTAPPA_PYTHON_EXECUTABLE")
    if env_py and Path(env_py).is_file():
        return env_py
    if Path(sys.executable).is_file():
        return sys.executable
    local_env = PROJECT_ROOT / "ai_system_env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if local_env.is_file():
        return str(local_env)
    raise RuntimeError("Kattappa Python executable could not be resolved.")

def run_shard(shard_data: dict, evidence_dir: Path) -> dict:
    shard_id = shard_data["shard_id"]
    iso_cls = shard_data["isolation_class"]
    node_ids = shard_data["node_ids"]

    # 8. Timeout must be mandatory in official manifests
    release_run_active = (os.environ.get("KATTAPPA_RELEASE_RUN_ACTIVE") == "1")
    if release_run_active and "timeout_seconds" not in shard_data:
        raise RuntimeError("Official shard is missing policy-resolved timeout")

    timeout_seconds = shard_data.get("timeout_seconds", 600)

    # Bind identity fields from shard_data
    run_id = shard_data.get("run_id")
    run_label = shard_data.get("run_label", "")
    candidate_commit = shard_data.get("candidate_commit")
    collection_hash = shard_data.get("collection_hash")
    policy_hash = shard_data.get("policy_hash")
    manifest_core_hash = shard_data.get("manifest_core_hash")
    manifest_file_hash = shard_data.get("manifest_file_hash")
    environment_hash = shard_data.get("environment_hash", "")

    shard_dir = evidence_dir / "shards" / shard_id
    shard_dir.mkdir(parents=True, exist_ok=True)

    result_json_path = shard_dir / "pytest_results.json"

    # Write expanded shard definition to JSON file (schema_version=1)
    shard_def_json = shard_dir / "shard_definition.json"
    shard_def_content = {
        "schema_version": 1,
        "shard_id": shard_id,
        "isolation_class": iso_cls,
        "run_id": run_id or "",
        "run_label": run_label or "",
        "candidate_commit": candidate_commit or "",
        "collection_hash": collection_hash or "",
        "policy_hash": policy_hash or "",
        "manifest_core_hash": manifest_core_hash or "",
        "manifest_file_hash": manifest_file_hash or "",
        "environment_hash": environment_hash or "",
        "timeout_seconds": timeout_seconds,
        "node_ids": node_ids
    }

    # Atomic write shard definition
    shard_def_tmp = shard_def_json.with_suffix(".json.tmp")
    with open(shard_def_tmp, "w", encoding="utf-8") as f:
        json.dump(shard_def_content, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(shard_def_tmp, shard_def_json)

    # Compute shard definition hash
    import hashlib
    shard_definition_sha256 = hashlib.sha256(shard_def_json.read_bytes()).hexdigest()

    # Write expected-node-ids.json atomically
    expected_node_ids_path = shard_dir / "expected-node-ids.json"
    if expected_node_ids_path.exists():
        expected_node_ids_path.unlink()
    eni_tmp = expected_node_ids_path.with_suffix(".json.tmp")
    with open(eni_tmp, "w", encoding="utf-8") as f:
        json.dump(node_ids, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(eni_tmp, expected_node_ids_path)
    # Validate
    reopened = json.loads(expected_node_ids_path.read_text(encoding="utf-8"))
    assert reopened == node_ids, "expected-node-ids.json content mismatch"
    expected_node_ids_sha256 = hashlib.sha256(expected_node_ids_path.read_bytes()).hexdigest()

    # Build launcher command with --run-identity if available
    run_identity_path = evidence_dir / "run-identity.json"
    cmd = [
        get_python_executable(),
        str(PROJECT_ROOT / "scripts" / "validation" / "execute_pytest_shard.py"),
        f"--shard-definition={shard_def_json}",
        f"--result-file={result_json_path}"
    ]
    if run_identity_path.exists():
        cmd.append(f"--run-identity={run_identity_path}")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["KATTAPPA_TEST_MODE"] = "true"
    env["KATTAPPA_RUN_ID"] = run_id or ""
    env["KATTAPPA_SHARD_ID"] = shard_id
    env["KATTAPPA_CANDIDATE_COMMIT"] = candidate_commit or ""

    # Check isolation config
    policy = load_shard_policy()
    cls_config = policy.isolation_classes.get(iso_cls, {})
    requires_isolated = cls_config.get("requires_isolated_storage", False)

    if requires_isolated:
        workspace_base = evidence_dir / "workspaces" / shard_id
        data_dir = workspace_base / "data"
        runtime_dir = workspace_base / "runtime"
        workspace_dir = workspace_base / "workspace"
        temp_dir = workspace_base / "temp"
        home_dir = workspace_base / "home"

        for d in [data_dir, runtime_dir, workspace_dir, temp_dir, home_dir]:
            d.mkdir(parents=True, exist_ok=True)

        data_path_str = str(data_dir.resolve())
        # Add a validation failure when two isolation-required shards share the same data root
        if data_path_str in USED_DATA_ROOTS:
            raise RuntimeError(f"Data root collision! Shard {shard_id} shares data root: {data_path_str}")
        USED_DATA_ROOTS.add(data_path_str)

        env["KATTAPPA_DATA_DIR"] = str(data_dir)
        env["KATTAPPA_RUNTIME_DIR"] = str(runtime_dir)
        env["KATTAPPA_WORKSPACE_DIR"] = str(workspace_dir)
        env["TMP"] = str(temp_dir)
        env["TEMP"] = str(temp_dir)

    stdout_path = shard_dir / "stdout.log"
    stderr_path = shard_dir / "stderr.log"

    # Pre-execution supervision snapshots
    ports_before = get_busy_ports()
    py_procs_before = get_python_processes()

    t0 = time.time()
    timed_out = False
    exit_code = -1

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

    with open(stdout_path, "w", encoding="utf-8") as out_f, open(stderr_path, "w", encoding="utf-8") as err_f:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=out_f,
            stderr=err_f,
            creationflags=creationflags
        )

        try:
            exit_code = proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_process_tree(proc.pid, timeout=10.0)
            exit_code = -9

    duration = time.time() - t0

    # Post-execution supervision cleanup
    kill_process_tree(proc.pid, timeout=2.0)

    # Check newly leaked ports and python processes
    ports_after = get_busy_ports()
    py_procs_after = get_python_processes()

    newly_leaked_ports = sorted(list(ports_after - ports_before))

    # Detached descendant tracking
    newly_spawned_py = py_procs_after - py_procs_before
    surviving_pids = []
    cleanup_log = []

    for sp_pid in newly_spawned_py:
        # Avoid checking current/parent process group
        if sp_pid != os.getpid() and sp_pid != proc.pid:
            try:
                p = psutil.Process(sp_pid)
                # Check if it was started in PROJECT_ROOT
                if p.cwd() == str(PROJECT_ROOT) or any(str(PROJECT_ROOT) in arg for arg in p.cmdline()):
                    # Terminate the orphan
                    p.kill()
                    surviving_pids.append(sp_pid)
                    cleanup_log.append(f"Killed orphaned python descendant process: {sp_pid}")
            except Exception as e:
                pass

    # Parse pytest plugin results
    executed_nodes = []
    attempted_nodes = []
    completed_nodes = []
    passed_cnt = 0
    failed_cnt = 0
    errors_cnt = 0
    skipped_cnt = 0
    xfailed_cnt = 0
    xpassed_cnt = 0
    internal_errors = []

    if result_json_path.exists():
        try:
            res_data = json.loads(result_json_path.read_text(encoding="utf-8"))
            attempted_nodes = res_data.get("attempted_node_ids", [])
            executed_nodes = res_data.get("executed_node_ids", [])
            completed_nodes = res_data.get("completed_node_ids", [])
            passed_cnt = res_data.get("passed", 0)
            failed_cnt = res_data.get("failed", 0)
            errors_cnt = res_data.get("errors", 0)
            skipped_cnt = res_data.get("skipped", 0)
            xfailed_cnt = res_data.get("xfailed", 0)
            xpassed_cnt = res_data.get("xpassed", 0)
            internal_errors = res_data.get("internal_errors", [])
        except Exception as e:
            internal_errors.append({"type": "ResultPluginParseError", "message": str(e)})

    # Fail shard closed if surviving processes or newly leaked ports are detected
    if surviving_pids or newly_leaked_ports:
        exit_code = -15 if exit_code == 0 else exit_code

    shard_result = {
        "run_id": run_id,
        "run_label": run_label,
        "candidate_commit": candidate_commit,
        "collection_hash": collection_hash,
        "policy_hash": policy_hash,
        "manifest_core_hash": manifest_core_hash,
        "manifest_file_hash": manifest_file_hash,
        "environment_hash": environment_hash,
        "shard_definition_sha256": shard_definition_sha256,
        "expected_node_ids_sha256": expected_node_ids_sha256,
        "shard_id": shard_id,
        "isolation_class": iso_cls,
        "total_nodes_assigned": len(node_ids),
        "total_nodes_attempted": len(attempted_nodes),
        "total_nodes_executed": len(executed_nodes),
        "total_nodes_completed": len(completed_nodes),
        "assigned_node_ids": node_ids,
        "attempted_node_ids": attempted_nodes,
        "executed_node_ids": executed_nodes,
        "completed_node_ids": completed_nodes,
        "passed": passed_cnt,
        "failed": failed_cnt,
        "errors": errors_cnt,
        "skipped": skipped_cnt,
        "xfailed": xfailed_cnt,
        "xpassed": xpassed_cnt,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": round(duration, 2),
        "supervision": {
            "surviving_pids": surviving_pids,
            "leaked_ports": newly_leaked_ports,
            "cleanup_log": "\n".join(cleanup_log)
        },
        "internal_errors": internal_errors
    }

    atomic_write_json(shard_dir / "shard-result.json", shard_result)

    status_str = "TIMEOUT" if timed_out else ("PASS" if exit_code == 0 else "FAIL")
    print(f"[{shard_id}] {status_str} in {duration:.1f}s | Executed: {len(executed_nodes)}/{len(node_ids)} | Passed: {passed_cnt} | Failed: {failed_cnt}")

    return shard_result

def atomic_write_json(path: Path, payload: dict):
    tmp_path = path.with_suffix(".json.tmp") if path.suffix == ".json" else Path(str(path) + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_test_shard.py <shard_json_path>")
        sys.exit(1)
    s_path = Path(sys.argv[1])
    s_data = json.loads(s_path.read_text(encoding="utf-8"))
    ev_dir = s_path.parents[1]
    run_shard(s_data, ev_dir)
