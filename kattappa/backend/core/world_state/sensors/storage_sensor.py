from __future__ import annotations
import shutil
from pathlib import Path
from backend.core.world_state.sensors.base_sensor import BaseSensor
from backend.core.config import load_config, runtime_data_root

class StorageSensor(BaseSensor):
    def collect(self) -> dict:
        config = load_config()
        ws_dir = Path(config.workspace_dir).resolve()
        trash_dir = runtime_data_root() / "backend" / "data" / "trash"
        
        free_bytes = 0
        try:
            # shutil.disk_usage returns (total, used, free) in bytes
            _, _, free_bytes = shutil.disk_usage(ws_dir)
        except Exception:
            pass
            
        return {
            "storage": {
                "free_space": free_bytes,
                "workspace_path": str(ws_dir),
                "trash_path": str(trash_dir)
            }
        }
