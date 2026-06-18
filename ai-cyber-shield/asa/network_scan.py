from __future__ import annotations

import ipaddress
import socket
import subprocess
import shutil
from dataclasses import dataclass, asdict
from typing import Any


DEFAULT_PORTS = (22, 53, 80, 135, 139, 443, 445, 3389, 5173, 8000, 8080, 11434)
MAX_PORTS = 50


@dataclass(frozen=True)
class PortObservation:
    host: str
    port: int
    state: str
    service_hint: str


def scan_local_network(
    target: str = "127.0.0.1",
    ports: str = "",
    timeout_seconds: float = 0.4,
    prefer_nmap: bool = True,
) -> dict[str, Any]:
    checked_target = _safe_target(target)
    checked_ports = _parse_ports(ports)
    nmap_path = shutil.which("nmap") if prefer_nmap else None
    if nmap_path:
        return _scan_with_nmap(nmap_path, checked_target, checked_ports)
    return _scan_with_socket(checked_target, checked_ports, timeout_seconds)


def _safe_target(target: str) -> str:
    value = (target or "127.0.0.1").strip()
    if value.lower() == "localhost":
        return "127.0.0.1"

    try:
        if "/" in value:
            network = ipaddress.ip_network(value, strict=False)
            if not _is_safe_address(network.network_address):
                raise ValueError("Only loopback, private, or link-local targets are allowed.")
            if network.version != 4 or network.prefixlen < 24:
                raise ValueError("CIDR scans are limited to IPv4 /24 or smaller local networks.")
            return str(network)

        address = ipaddress.ip_address(value)
        if not _is_safe_address(address):
            raise ValueError("Only loopback, private, or link-local targets are allowed.")
        return str(address)
    except ValueError as exc:
        if "Only loopback" in str(exc) or "CIDR scans" in str(exc):
            raise
        raise ValueError("Target must be localhost, a private IP, a loopback IP, or a small private CIDR.") from exc


def _is_safe_address(address: ipaddress._BaseAddress) -> bool:
    return address.is_loopback or address.is_private or address.is_link_local


def _parse_ports(raw_ports: str) -> list[int]:
    if not raw_ports.strip():
        return list(DEFAULT_PORTS)

    ports: set[int] = set()
    for part in raw_ports.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if end < start:
                raise ValueError("Port ranges must be increasing.")
            ports.update(range(start, end + 1))
        else:
            ports.add(int(part))

    valid_ports = sorted(port for port in ports if 1 <= port <= 65535)
    if not valid_ports:
        raise ValueError("At least one valid TCP port is required.")
    if len(valid_ports) > MAX_PORTS:
        raise ValueError(f"Port scans are limited to {MAX_PORTS} ports per run.")
    return valid_ports


def _scan_with_nmap(nmap_path: str, target: str, ports: list[int]) -> dict[str, Any]:
    command = [
        nmap_path,
        "-Pn",
        "-T3",
        "--open",
        "-p",
        ",".join(str(port) for port in ports),
        target,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    observations = _parse_nmap_text(target, result.stdout)
    return {
        "engine": "nmap_optional_adapter",
        "target": target,
        "ports_checked": ports,
        "safe_scope": "loopback_private_or_link_local_only",
        "network_required": False,
        "returncode": result.returncode,
        "observations": [asdict(item) for item in observations],
        "raw_summary": "\n".join(result.stdout.splitlines()[:80]),
        "warnings": _nmap_warnings(result.stderr),
    }


def _scan_with_socket(target: str, ports: list[int], timeout_seconds: float) -> dict[str, Any]:
    if "/" in target:
        raise ValueError("CIDR scans need Nmap installed. Socket fallback scans one local host at a time.")

    observations: list[PortObservation] = []
    for port in ports:
        state = "closed"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(max(0.05, min(timeout_seconds, 3.0)))
            try:
                if sock.connect_ex((target, port)) == 0:
                    state = "open"
            except OSError:
                state = "unreachable"
        if state == "open":
            observations.append(PortObservation(target, port, state, _service_hint(port)))

    return {
        "engine": "python_socket_local_port_scan",
        "target": target,
        "ports_checked": ports,
        "safe_scope": "loopback_private_or_link_local_only",
        "network_required": False,
        "observations": [asdict(item) for item in observations],
        "raw_summary": "",
        "warnings": ["Nmap was not found, so a limited local TCP connect scan was used."],
    }


def _parse_nmap_text(target: str, output: str) -> list[PortObservation]:
    observations: list[PortObservation] = []
    current_host = target
    for line in output.splitlines():
        if line.startswith("Nmap scan report for "):
            current_host = line.removeprefix("Nmap scan report for ").strip()
            continue
        if "/tcp" not in line or " open " not in line:
            continue
        columns = line.split()
        if len(columns) < 2:
            continue
        port_text = columns[0].split("/", 1)[0]
        try:
            port = int(port_text)
        except ValueError:
            continue
        service = columns[2] if len(columns) >= 3 else _service_hint(port)
        observations.append(PortObservation(current_host, port, "open", service))
    return observations


def _service_hint(port: int) -> str:
    hints = {
        22: "ssh",
        53: "dns",
        80: "http",
        135: "msrpc",
        139: "netbios",
        443: "https",
        445: "smb",
        3389: "rdp",
        5173: "vite",
        8000: "dev-api",
        8080: "http-alt",
        11434: "ollama",
    }
    return hints.get(port, "tcp")


def _nmap_warnings(stderr: str) -> list[str]:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return lines[:20]
