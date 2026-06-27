import os
import json
import hashlib
import subprocess
import platform
import time
from pathlib import Path

def get_git_commit():
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "unknown"

def get_configs_hash(configs_dir):
    configs_path = Path(configs_dir)
    if not configs_path.exists():
        return "unknown-configs-dir"
    
    sha256 = hashlib.sha256()
    # Sort files to ensure deterministic hashing
    for p in sorted(configs_path.rglob("*.json")):
        try:
            with open(p, "rb") as f:
                sha256.update(f.read())
        except Exception:
            pass
    return sha256.hexdigest()

def get_hardware_profile():
    system = platform.system()
    if system == "Darwin":
        try:
            res = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True)
            if res.returncode == 0:
                cpu = res.stdout.strip()
            else:
                cpu = platform.processor()
            # Try to get memory
            res_mem = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True)
            if res_mem.returncode == 0:
                mem_gb = int(res_mem.stdout.strip()) / (1024**3)
                mem = f"{mem_gb:.0f}GB Unified Memory"
            else:
                mem = ""
            return f"Apple {cpu} ({mem})"
        except Exception:
            pass
    return f"{platform.system()} {platform.processor()} {platform.machine()}"

def log_experiment(
    experiment_id: str,
    configs_dir: str,
    dataset_version: str,
    tokenizer_version: str,
    learning_rate_curve: list,
    loss_curve: list,
    evaluation_scorecard: dict,
    notes: str = ""
):
    git_commit = get_git_commit()
    config_hash = get_configs_hash(configs_dir)
    hardware = get_hardware_profile()
    
    record = {
        "experiment_id": experiment_id,
        "git_commit": git_commit,
        "config_hash": config_hash,
        "dataset_version": dataset_version,
        "tokenizer_version": tokenizer_version,
        "hardware_profile": hardware,
        "learning_rate_curve": learning_rate_curve,
        "loss_curve": loss_curve,
        "evaluation_scorecard": evaluation_scorecard,
        "notes": notes,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    
    out_dir = Path(__file__).parent.parent.parent / "kattappa_data_engine/reports/experiments"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    out_file = out_dir / f"{experiment_id}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
        
    print(f"Logged experiment {experiment_id} successfully to {out_file}")
    return record
