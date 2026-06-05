from __future__ import annotations

import socket

from .config import ASAConfig
from .models import ActionResult


class HardeningLayer:
    def __init__(self, config: ASAConfig) -> None:
        self.config = config

    def audit(self) -> list[ActionResult]:
        results: list[ActionResult] = []
        results.append(self._audit_blocklist())
        results.append(self._audit_honeypot())
        results.extend(self._audit_common_local_ports())
        return results

    def _audit_blocklist(self) -> ActionResult:
        exists = self.config.blocklist_file.exists()
        return ActionResult(
            "audit_blocklist",
            exists,
            "Local blocklist exists" if exists else "Local blocklist is missing",
            {"path": str(self.config.blocklist_file)},
        )

    def _audit_honeypot(self) -> ActionResult:
        exists = self.config.honeypot_dir.exists() and any(self.config.honeypot_dir.iterdir())
        return ActionResult(
            "audit_honeypot",
            exists,
            "Honeypot files exist" if exists else "Honeypot files are missing",
            {"path": str(self.config.honeypot_dir)},
        )

    def _audit_common_local_ports(self) -> list[ActionResult]:
        checks = []
        for port in (22, 23, 3389, 5900):
            open_local = self._port_open("127.0.0.1", port)
            checks.append(
                ActionResult(
                    "audit_local_port",
                    not open_local,
                    "Common remote access port is closed"
                    if not open_local
                    else "Common remote access port is open; review whether it is needed",
                    {"host": "127.0.0.1", "port": port},
                )
            )
        return checks

    def _port_open(self, host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex((host, port)) == 0

