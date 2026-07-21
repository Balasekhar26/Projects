import os
import sys
import json
import time
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(r"C:\Users\balu\Projects\kattappa").resolve()

def run_shard(shard_data: dict, evidence_dir: Path) -> dict:
    shard_id = shard_data["shard_id"]
    nodes = shard_data["node_ids"]
    cls = shard_data["isolation_class"]

    shard_dir = evidence_dir / "shards" / shard_id
    shard_dir.mkdir(parents=True, exist_ok=True)

    # Isolated temp directories
    with tempfile.TemporaryDirectory(prefix=f"kattappa_shard_{shard_id}_data_") as tmp_data, \
         tempfile.TemporaryDirectory(prefix=f"kattappa_shard_{shard_id}_runtime_") as tmp_runtime:
        
        env = dict(os.environ)
        env["KATTAPPA_TEST_MODE"] = "true"
        env["KATTAPPA_DATA_DIR"] = tmp_data
        env["KATTAPPA_RUNTIME_DIR"] = tmp_runtime
        env["TEMP"] = tmp_data
        env["TMP"] = tmp_data

        # Pass node IDs via command file or arguments
        cmd_args = [sys.executable, "-m", "pytest", "-q", "--tb=line"] + nodes

        t0 = time.perf_counter()
        proc = subprocess.run(cmd_args, cwd=str(ROOT), capture_output=True, text=True, env=env)
        elapsed = time.perf_counter() - t0

        stdout = proc.stdout
        stderr = proc.stderr
        exit_code = proc.returncode

        (shard_dir / "stdout.log").write_text(stdout, encoding="utf-8")
        (shard_dir / "stderr.log").write_text(stderr, encoding="utf-8")

        # Parse passed count from stdout
        passed = 0
        failed = 0
        if "passed" in stdout:
            import re
            m_pass = re.search(r"(\d+) passed", stdout)
            if m_pass:
                passed = int(m_pass.group(1))
            m_fail = re.search(r"(\d+) failed", stdout)
            if m_fail:
                failed = int(m_fail.group(1))

        res = {
            "shard_id": shard_id,
            "isolation_class": cls,
            "total_nodes": len(nodes),
            "passed": passed,
            "failed": failed,
            "exit_code": exit_code,
            "duration_seconds": round(elapsed, 2)
        }

        with open(shard_dir / "shard-result.json", "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)

        print(f"[{shard_id}] Status: {'PASS' if exit_code == 0 else 'FAIL'} | Passed: {passed}/{len(nodes)} | Duration: {elapsed:.2f}s")
        return res

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_test_shard.py <shard_id>")
        sys.exit(1)
    target_id = sys.argv[1]
    out_dir = ROOT / "docs" / "evidence" / "k-r0.5"
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    target_shard = next((s for s in manifest["shards"] if s["shard_id"] == target_id), None)
    if not target_shard:
        print(f"Shard {target_id} not found in manifest")
        sys.exit(1)
    run_shard(target_shard, out_dir)
