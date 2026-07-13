from __future__ import annotations

import json
import os
import platform
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict

from backend.core.config import load_config
from backend.core.logger import read_log


def collect_system_info() -> Dict[str, Any]:
    """Collects hardware and OS specifications."""
    info = {
        "timestamp_utc": time.time(),
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "python_version": sys.version,
    }
    try:
        import psutil
        ram = psutil.virtual_memory()
        info.update({
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "ram_total_gb": round(ram.total / (1024 ** 3), 2),
            "ram_available_gb": round(ram.available / (1024 ** 3), 2),
        })
    except ImportError:
        info["psutil_available"] = False
        info["cpu_count"] = os.cpu_count()
    return info


def export_diagnostics_bundle() -> Path:
    """Generates a zipped diagnostics package containing logs, database queries, and system specs."""
    config = load_config()
    
    # 1. Collect specs
    try:
        sys_info = collect_system_info()
    except Exception as e:
        sys_info = {"error": f"Failed to collect system info: {e}", "timestamp_utc": time.time()}

    # 2. Collect sqlite metrics database records if available
    metrics_dump: Dict[str, Any] = {}
    try:
        from backend.core.cos.kernel import KERNEL
        if KERNEL and KERNEL.ledger:
            # Gather statistics for key metrics
            for name in ["perceive_latency", "retrieve_latency", "reason_latency", "plan_latency", "act_latency", "learn_latency", "cpu_usage", "memory_usage", "tokens_consumed"]:
                vals = KERNEL.ledger.get_metric_values(name)
                metrics_dump[name] = vals[-100:]  # Grab last 100 historical entries
    except Exception as e:
        metrics_dump["error"] = f"Failed to dump ledger metrics: {e}"

    # 3. Read log tail
    try:
        log_lines = read_log(limit=200)
    except Exception as e:
        log_lines = [f"Failed to read agent.log: {e}"]

    # 4. Write to temp file & create Zip
    diag_dir = config.logs_dir / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    zip_path = diag_dir / f"kattappa_diagnostics_{timestamp}.zip"
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # Write system info
        zip_file.writestr("system_info.json", json.dumps(sys_info, indent=2))
        # Write metrics
        zip_file.writestr("metrics_history.json", json.dumps(metrics_dump, indent=2))
        # Write agent log tail
        zip_file.writestr("agent_log_tail.txt", "\n".join(log_lines))
        
    return zip_path
