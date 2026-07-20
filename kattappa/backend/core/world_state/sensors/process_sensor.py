from __future__ import annotations
import subprocess
import sys
from backend.core.world_state.sensors.base_sensor import BaseSensor

class ProcessSensor(BaseSensor):
    def collect(self) -> dict:
        processes = []
        try:
            if sys.platform == "win32":
                res = subprocess.run(
                    ["tasklist", "/nh", "/fo", "csv"],
                    capture_output=True,
                    text=True,
                    timeout=2.5
                )
                if res.returncode == 0:
                    for line in res.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if parts:
                            name = parts[0].replace('"', '').strip().lower()
                            if name:
                                processes.append(name)
            else:
                res = subprocess.run(
                    ["ps", "-eo", "comm"],
                    capture_output=True,
                    text=True,
                    timeout=2.5
                )
                if res.returncode == 0:
                    for line in res.stdout.strip().split("\n"):
                        name = line.strip().lower()
                        if name:
                            processes.append(name)
        except Exception:
            pass
            
        # Deduplicate
        processes = sorted(list(set(processes)))
        
        # Keep payload tiny by filtering for known processes Kattappa automates
        known_targets = {
            "code.exe", "chrome.exe", "ollama.exe", "python.exe", "cmd.exe", "powershell.exe",
            "code", "chrome", "google-chrome", "ollama", "python", "sh", "bash"
        }
        running_targets = [p for p in processes if p in known_targets]
        
        return {
            "processes": {
                "running": running_targets,
                "chrome_open": any("chrome" in p for p in running_targets),
                "vscode_open": any("code" in p for p in running_targets),
                "ollama_running": any("ollama" in p for p in running_targets)
            }
        }
