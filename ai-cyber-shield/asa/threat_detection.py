from __future__ import annotations

from collections import Counter
from pathlib import Path

from .attribution import build_attribution_hint
from .config import ASAConfig
from .learning import BaselineStore
from .models import ProcessInfo, SystemMap, ThreatFinding


class ThreatDetectionEngine:
    def __init__(self, config: ASAConfig, baseline: BaselineStore | None = None) -> None:
        self.config = config
        self.baseline = baseline

    def analyze(self, system_map: SystemMap) -> list[ThreatFinding]:
        findings: list[ThreatFinding] = []
        findings.extend(self._process_findings(system_map.processes))
        findings.extend(self._network_findings(system_map))
        findings.extend(self._startup_findings(system_map))
        findings.extend(self._baseline_deviation_findings(system_map))
        return sorted(findings, key=lambda item: item.score, reverse=True)

    def _process_findings(self, processes: list[ProcessInfo]) -> list[ThreatFinding]:
        findings: list[ThreatFinding] = []
        for process in processes:
            lower_name = process.name.lower()
            lower_exe = process.exe.lower()
            if any(pattern in lower_name for pattern in self.config.suspicious_process_patterns):
                findings.append(
                    ThreatFinding(
                        level="high",
                        score=90,
                        kind="suspicious_process_name",
                        message="Suspicious process name detected",
                        evidence=vars(process),
                        reversible_action=f"review or contain pid {process.pid}",
                    )
                )

            if self._path_is_risky(process.exe):
                findings.append(
                    ThreatFinding(
                        level="medium",
                        score=60,
                        kind="process_from_risky_path",
                        message="Process is running from a risky writable path",
                        evidence=vars(process),
                        reversible_action=f"review or contain pid {process.pid}",
                    )
                )

            if process.cpu_percent >= self.config.max_cpu_percent:
                findings.append(
                    ThreatFinding(
                        level="warning",
                        score=70,
                        kind="high_cpu_process",
                        message="Process exceeded CPU threshold",
                        evidence=vars(process),
                    )
                )

            if process.memory_percent >= self.config.max_memory_percent:
                findings.append(
                    ThreatFinding(
                        level="warning",
                        score=70,
                        kind="high_memory_process",
                        message="Process exceeded memory threshold",
                        evidence=vars(process),
                    )
                )
        return findings

    def _network_findings(self, system_map: SystemMap) -> list[ThreatFinding]:
        findings: list[ThreatFinding] = []
        counts = Counter(conn.pid for conn in system_map.network_connections if conn.pid)
        blocklist = self._blocklist()

        for conn in system_map.network_connections:
            if conn.remote_port in self.config.suspicious_remote_ports:
                attribution = build_attribution_hint(conn.remote_ip)
                findings.append(
                    ThreatFinding(
                        level="high",
                        score=85,
                        kind="suspicious_remote_port",
                        message="Connection to suspicious remote port",
                        evidence=vars(conn) | {"attribution": attribution.to_dict()},
                        reversible_action=f"locally block ip {conn.remote_ip}",
                    )
                )
            if conn.remote_ip in blocklist:
                attribution = build_attribution_hint(conn.remote_ip)
                findings.append(
                    ThreatFinding(
                        level="critical",
                        score=95,
                        kind="blocked_ip_connection",
                        message="Connection to a locally blocked IP detected",
                        evidence=vars(conn) | {"attribution": attribution.to_dict()},
                        reversible_action=f"contain pid {conn.pid}",
                    )
                )

        for pid, count in counts.items():
            if count >= self.config.max_connections_per_process:
                findings.append(
                    ThreatFinding(
                        level="warning",
                        score=65,
                        kind="connection_fanout",
                        message="Process has many established network connections",
                        evidence={"pid": pid, "connection_count": count},
                    )
                )
        return findings

    def _startup_findings(self, system_map: SystemMap) -> list[ThreatFinding]:
        findings: list[ThreatFinding] = []
        for entry in system_map.startup_entries:
            if entry.age_hours <= 48:
                findings.append(
                    ThreatFinding(
                        level="low",
                        score=35,
                        kind="recent_startup_entry",
                        message="Recently modified startup entry found",
                        evidence={
                            "path": str(entry.path),
                            "age_hours": round(entry.age_hours, 2),
                        },
                    )
                )
        return findings

    def _baseline_deviation_findings(self, system_map: SystemMap) -> list[ThreatFinding]:
        if self.baseline is None or not self.baseline.exists():
            return []
        baseline = self.baseline.load()
        known_processes = set(baseline.get("process_names", []))
        findings: list[ThreatFinding] = []
        for process in system_map.processes:
            if process.name and process.name not in known_processes and self._path_is_risky(process.exe):
                findings.append(
                    ThreatFinding(
                        level="medium",
                        score=70,
                        kind="new_risky_process",
                        message="New process outside baseline is running from a risky path",
                        evidence=vars(process),
                        reversible_action=f"review or contain pid {process.pid}",
                    )
                )
        return findings

    def _path_is_risky(self, exe: str) -> bool:
        if not exe:
            return False
        executable = Path(exe).expanduser()
        for risky_path in self.config.risky_process_paths:
            try:
                executable.relative_to(risky_path)
                return True
            except ValueError:
                continue
        return False

    def _blocklist(self) -> set[str]:
        if not self.config.blocklist_file.exists():
            return set()
        return {
            line.strip()
            for line in self.config.blocklist_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
