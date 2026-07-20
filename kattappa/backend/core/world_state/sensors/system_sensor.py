from __future__ import annotations
import platform
import time
from datetime import datetime
from backend.core.world_state.sensors.base_sensor import BaseSensor

class SystemSensor(BaseSensor):
    def collect(self) -> dict:
        uptime = 0.0
        try:
            import ctypes
            # GetTickCount64 returns milliseconds since boot on Windows
            uptime = ctypes.windll.kernel32.GetTickCount64() / 1000.0
        except Exception:
            # Unix fallback check (read /proc/uptime)
            try:
                with open("/proc/uptime", "r") as f:
                    uptime = float(f.readline().split()[0])
            except Exception:
                uptime = 3600.0  # Fallback constant
                
        return {
            "system": {
                "os_name": platform.system(),
                "os_version": platform.release(),
                "hostname": platform.node(),
                "uptime": uptime,
                "timezone": str(datetime.now().astimezone().tzname() or "UTC")
            }
        }
