from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .config import ASAConfig
from .models import FileObservation, NetworkConnection, ProcessInfo, StartupEntry, SystemMap

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None


class SystemMapper:
    def __init__(self, config: ASAConfig) -> None:
        self.config = config

    def build(self) -> SystemMap:
        processes = self.processes()
        connections = self.network_connections(processes)
        startup_entries = self.startup_entries()
        file_observations = self.file_observations()
        return SystemMap(processes, connections, startup_entries, file_observations)

    def processes(self) -> list[ProcessInfo]:
        if psutil is not None:
            return self._processes_psutil()
        return self._processes_ps()

    def _processes_psutil(self) -> list[ProcessInfo]:
        items: list[ProcessInfo] = []
        for process in psutil.process_iter(["pid", "username", "name", "exe"]):
            try:
                info = process.info
                items.append(
                    ProcessInfo(
                        pid=int(info.get("pid") or 0),
                        user=str(info.get("username") or ""),
                        name=str(info.get("name") or ""),
                        exe=str(info.get("exe") or ""),
                        cpu_percent=float(process.cpu_percent(interval=None) or 0.0),
                        memory_percent=float(process.memory_percent() or 0.0),
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return items

    def _processes_ps(self) -> list[ProcessInfo]:
        command = ["ps", "-axo", "pid=,user=,%cpu=,%mem=,comm="]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        items: list[ProcessInfo] = []
        for line in result.stdout.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 5:
                continue
            pid, user, cpu, mem, exe = parts
            try:
                items.append(
                    ProcessInfo(
                        pid=int(pid),
                        user=user,
                        name=Path(exe).name,
                        exe=exe,
                        cpu_percent=float(cpu),
                        memory_percent=float(mem),
                    )
                )
            except ValueError:
                continue
        return items

    def network_connections(self, processes: list[ProcessInfo]) -> list[NetworkConnection]:
        pid_to_name = {item.pid: item.name for item in processes}
        if psutil is not None:
            return self._network_psutil(pid_to_name)
        return self._network_lsof()

    def _network_psutil(self, pid_to_name: dict[int, str]) -> list[NetworkConnection]:
        items: list[NetworkConnection] = []
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status != "ESTABLISHED" or not conn.raddr:
                continue
            remote_ip = str(conn.raddr.ip)
            remote_port = int(conn.raddr.port)
            local = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else ""
            items.append(
                NetworkConnection(
                    pid=conn.pid,
                    process_name=pid_to_name.get(conn.pid or -1, ""),
                    local_address=local,
                    remote_address=f"{remote_ip}:{remote_port}",
                    remote_ip=remote_ip,
                    remote_port=remote_port,
                    status=conn.status,
                )
            )
        return items

    def _network_lsof(self) -> list[NetworkConnection]:
        if not _command_exists("lsof"):
            return []
        command = ["lsof", "-nP", "-iTCP", "-sTCP:ESTABLISHED"]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        items: list[NetworkConnection] = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 9 or "->" not in parts[-1]:
                continue
            process_name = parts[0]
            try:
                pid = int(parts[1])
            except ValueError:
                pid = None
            remote = parts[-1].split("->", 1)[1]
            remote_ip, remote_port = _split_host_port(remote)
            items.append(
                NetworkConnection(
                    pid=pid,
                    process_name=process_name,
                    local_address=parts[-1].split("->", 1)[0],
                    remote_address=remote,
                    remote_ip=remote_ip,
                    remote_port=remote_port,
                    status="ESTABLISHED",
                )
            )
        return items

    def startup_entries(self) -> list[StartupEntry]:
        now = time.time()
        entries: list[StartupEntry] = []
        for directory in self.config.critical_file_paths:
            if not directory.exists() or not directory.is_dir():
                continue
            for path in directory.glob("*.plist"):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                age_hours = (now - stat.st_mtime) / 3600
                entries.append(StartupEntry(path, stat.st_mtime, age_hours))
        return entries

    def file_observations(self) -> list[FileObservation]:
        observations: list[FileObservation] = []
        for path in self.config.critical_file_paths:
            try:
                stat = path.stat()
                observations.append(
                    FileObservation(
                        path=path,
                        exists=True,
                        is_file=path.is_file(),
                        modified_time=stat.st_mtime,
                        size_bytes=stat.st_size,
                    )
                )
            except OSError:
                observations.append(FileObservation(path=path, exists=False, is_file=False))
        return observations


def _split_host_port(value: str) -> tuple[str, int | None]:
    host, _, port_text = value.rpartition(":")
    if not host:
        return value, None
    try:
        return host, int(port_text)
    except ValueError:
        return host, None


def _command_exists(name: str) -> bool:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return True
    return False
