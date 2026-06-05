from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import ASAConfig
from .models import SystemMap


class BaselineStore:
    def __init__(self, config: ASAConfig) -> None:
        self.config = config

    def exists(self) -> bool:
        return self.config.baseline_file.exists()

    def load(self) -> dict[str, Any]:
        if not self.exists():
            return {}
        return json.loads(self.config.baseline_file.read_text(encoding="utf-8"))

    def save(self, system_map: SystemMap) -> None:
        self.config.ensure_dirs()
        payload = {
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "process_names": sorted({item.name for item in system_map.processes if item.name}),
            "remote_ips": sorted(
                {item.remote_ip for item in system_map.network_connections if item.remote_ip}
            ),
            "startup_entries": sorted(str(item.path) for item in system_map.startup_entries),
        }
        self.config.baseline_file.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

