from __future__ import annotations
import os
import platform
import subprocess
from backend.core.world_state.sensors.base_sensor import BaseSensor

class HardwareSensor(BaseSensor):
    def collect(self) -> dict:
        cpu_cores = os.cpu_count() or 1
        cpu_model = platform.processor() or "Unknown CPU"
        
        ram_total = 8.0 * (1024 ** 3)  # default 8 GB
        ram_available = 4.0 * (1024 ** 3)  # default 4 GB
        
        # Windows Native memory queries using ctypes
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                ram_total = stat.ullTotalPhys
                ram_available = stat.ullAvailPhys
        except Exception:
            # Fallback for Linux or macOS
            try:
                with open("/proc/meminfo", "r") as f:
                    lines = f.readlines()
                mem_total_kb = 0
                mem_free_kb = 0
                for line in lines:
                    if line.startswith("MemTotal:"):
                        mem_total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:") or line.startswith("MemFree:"):
                        mem_free_kb = int(line.split()[1])
                if mem_total_kb:
                    ram_total = mem_total_kb * 1024
                    ram_available = mem_free_kb * 1024
            except Exception:
                pass
                
        # Basic GPU detection via nvidia-smi command line check
        gpu_name = "Integrated Graphics"
        gpu_vram = 0
        try:
            res = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split(",")
                if len(parts) >= 2:
                    gpu_name = parts[0].strip()
                    gpu_vram = int(parts[1].strip()) * (1024 * 1024)  # convert to bytes
        except Exception:
            pass

        return {
            "hardware": {
                "cpu_model": cpu_model,
                "cpu_cores": cpu_cores,
                "ram_total": ram_total,
                "ram_available": ram_available,
                "gpu_name": gpu_name,
                "gpu_vram": gpu_vram
            }
        }
