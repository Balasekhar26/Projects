import sys
import os
import json
import time
import socket
import psutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def check_known_ports_free(ports: list[int] = None) -> list[int]:
    if ports is None:
        ports = [8000, 8080, 8443, 9090]
    leaked_ports = []
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                leaked_ports.append(port)
    return leaked_ports

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

        # Wait up to 10 seconds for process tree termination
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
    timeout_seconds = shard_data.get("timeout_seconds", 300)

    shard_dir = evidence_dir / "shards" / shard_id
    shard_dir.mkdir(parents=True, exist_ok=True)

    result_json_path = shard_dir / "pytest_results.json"
    
    cmd = [
        get_python_executable(),
        "-m", "pytest",
        "-p", "scripts.validation.pytest_result_plugin",
        f"--kattappa-result-file={result_json_path}"
    ] + node_ids

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["KATTAPPA_TEST_MODE"] = "true"

    stdout_path = shard_dir / "stdout.log"
    stderr_path = shard_dir / "stderr.log"

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
            tk_rc, surviving_pids, cleanup_msg = kill_process_tree(proc.pid, timeout=10.0)
            exit_code = -9

    duration = time.time() - t0

    # Post-execution supervision check
    tk_rc, surviving_pids, cleanup_msg = kill_process_tree(proc.pid, timeout=2.0)
    leaked_ports = check_known_ports_free()

    # Parse KattappaResultPlugin output
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

    # Fail shard if surviving process or port leak detected
    if surviving_pids or leaked_ports:
        exit_code = -15 if exit_code == 0 else exit_code

    shard_result = {
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
            "leaked_ports": leaked_ports,
            "cleanup_log": cleanup_msg
        },
        "internal_errors": internal_errors
    }

    with open(shard_dir / "shard-result.json", "w", encoding="utf-8") as f:
        json.dump(shard_result, f, indent=2)

    status_str = "TIMEOUT" if timed_out else ("PASS" if exit_code == 0 else "FAIL")
    print(f"[{shard_id}] {status_str} in {duration:.1f}s | Executed: {len(executed_nodes)}/{len(node_ids)} | Passed: {passed_cnt} | Failed: {failed_cnt}")

    return shard_result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_test_shard.py <shard_json_path>")
        sys.exit(1)
    s_path = Path(sys.argv[1])
    s_data = json.loads(s_path.read_text(encoding="utf-8"))
    ev_dir = s_path.parents[1]
    run_shard(s_data, ev_dir)
