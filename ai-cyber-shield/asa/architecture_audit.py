from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import ASAConfig


@dataclass(frozen=True)
class AuditCheck:
    layer: str
    target: str
    ok: bool
    message: str


class ArchitectureAudit:
    """Checks whether the ASA still matches the intended defensive architecture."""

    def __init__(self, config: ASAConfig) -> None:
        self.config = config

    def run(self) -> list[AuditCheck]:
        root = self.config.root
        return [
            self._file("entry_scan", root / "asa" / "system_map.py", "System mapper exists"),
            self._file("threat_detection", root / "asa" / "threat_detection.py", "Threat detection engine exists"),
            self._file("self_healing", root / "asa" / "self_healing.py", "Self-healing engine exists"),
            self._file("hardening", root / "asa" / "hardening.py", "Hardening layer exists"),
            self._file("continuous_monitoring", root / "asa" / "monitoring.py", "Monitoring loop exists"),
            self._file("response", root / "asa" / "response.py", "Response engine exists"),
            self._file("learning", root / "asa" / "learning.py", "Baseline learning exists"),
            self._file("logging", root / "asa" / "logging_engine.py", "Evidence logger exists"),
            self._file("reporting", root / "asa" / "reporting.py", "Report writer exists"),
            self._policy("response.dry_run", self.config.response.dry_run, "Response defaults to reversible dry-run"),
            self._policy("response.auto_contain", not self.config.response.auto_contain, "Auto-containment is disabled by default"),
            self._policy("protected_process_names", bool(self.config.protected_process_names), "Protected process list is configured"),
        ]

    def _file(self, layer: str, path: Path, message: str) -> AuditCheck:
        exists = path.exists()
        return AuditCheck(
            layer=layer,
            target=str(path.relative_to(self.config.root)),
            ok=exists,
            message=message if exists else f"Missing {message.lower()}",
        )

    def _policy(self, target: str, ok: bool, message: str) -> AuditCheck:
        return AuditCheck(
            layer="safety_policy",
            target=target,
            ok=ok,
            message=message if ok else f"Policy risk: {message.lower()}",
        )
