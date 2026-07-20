from __future__ import annotations
import shutil
import subprocess
from backend.core.world_state.sensors.base_sensor import BaseSensor

class CapabilitySensor(BaseSensor):
    def collect(self) -> dict:
        cuda = False
        try:
            res = subprocess.run(["nvidia-smi"], capture_output=True, timeout=1.0)
            cuda = (res.returncode == 0)
        except Exception:
            pass
            
        capabilities = {
            "git": shutil.which("git") is not None,
            "docker": shutil.which("docker") is not None,
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "node": shutil.which("node") is not None,
            "cuda": cuda,
            "ollama": shutil.which("ollama") is not None or shutil.which("ollama.exe") is not None,
            "chrome": shutil.which("chrome") is not None or shutil.which("chrome.exe") is not None or shutil.which("google-chrome") is not None,
        }
        
        return {
            "capabilities": capabilities
        }
