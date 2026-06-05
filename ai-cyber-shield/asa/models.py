from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    user: str
    name: str
    exe: str
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    connection_count: int = 0


@dataclass(frozen=True)
class NetworkConnection:
    pid: int | None
    process_name: str
    local_address: str
    remote_address: str
    remote_ip: str
    remote_port: int | None
    status: str


@dataclass(frozen=True)
class StartupEntry:
    path: Path
    modified_time: float
    age_hours: float


@dataclass(frozen=True)
class FileObservation:
    path: Path
    exists: bool
    is_file: bool
    modified_time: float | None = None
    size_bytes: int | None = None


@dataclass
class SystemMap:
    processes: list[ProcessInfo] = field(default_factory=list)
    network_connections: list[NetworkConnection] = field(default_factory=list)
    startup_entries: list[StartupEntry] = field(default_factory=list)
    file_observations: list[FileObservation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "processes": [vars(item) for item in self.processes],
            "network_connections": [vars(item) for item in self.network_connections],
            "startup_entries": [
                {
                    "path": str(item.path),
                    "modified_time": item.modified_time,
                    "age_hours": item.age_hours,
                }
                for item in self.startup_entries
            ],
            "file_observations": [
                {
                    "path": str(item.path),
                    "exists": item.exists,
                    "is_file": item.is_file,
                    "modified_time": item.modified_time,
                    "size_bytes": item.size_bytes,
                }
                for item in self.file_observations
            ],
        }


@dataclass(frozen=True)
class ThreatFinding:
    level: str
    score: int
    kind: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    reversible_action: str | None = None


@dataclass(frozen=True)
class ActionResult:
    action: str
    ok: bool
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

