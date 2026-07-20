from __future__ import annotations
import os
import sys
from backend.core.world_state.sensors.base_sensor import BaseSensor

class PythonSensor(BaseSensor):
    def collect(self) -> dict:
        active_venv = os.getenv("VIRTUAL_ENV") or sys.prefix
        
        installed = []
        try:
            from importlib.metadata import distributions
            # Retrieve unique distribution names installed in sys.path
            installed = sorted(list(set(
                d.metadata["Name"].lower()
                for d in distributions()
                if d.metadata and d.metadata.get("Name")
            )))
        except Exception:
            pass
            
        return {
            "python": {
                "python_version": sys.version.split()[0],
                "active_venv": active_venv,
                "installed_packages": installed,
                "available_interpreters": [sys.executable]
            }
        }
