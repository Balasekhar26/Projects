"""Authoritative, idempotent lifecycle management for the development backend."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_DIR = ROOT / ".kattappa" / "runtime"
DEFAULT_METADATA = DEFAULT_RUNTIME_DIR / "backend.state.json"


@dataclass(frozen=True)
class RuntimePaths:
    state: Path
    pid: Path
    port: Path
    log: Path

    @classmethod
    def from_metadata(cls, metadata_path: Path) -> "RuntimePaths":
        state = metadata_path.resolve()
        return cls(
            state=state,
            pid=state.parent / "backend.pid",
            port=state.parent / "backend.port",
            log=state.parent / "backend.log",
        )


@dataclass(frozen=True)
class BackendProcessMetadata:
    pid: int
    port: int
    cwd: str
    command: str
    argv: list[str]
    started_at: str
    started_epoch: float
    git_checkout: str
    state: str = "running"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BackendProcessMetadata":
        if not isinstance(payload, dict):
            raise RuntimeError("backend state must be a JSON object")
        try:
            return cls(**payload)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"invalid backend state: {exc}") from exc


def _atomic_write(path: Path, content: str) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def write_metadata(metadata: BackendProcessMetadata, path: Path) -> None:
    _atomic_write(path, json.dumps(asdict(metadata), indent=2) + "\n")


def write_runtime_state(metadata: BackendProcessMetadata, paths: RuntimePaths) -> None:
    write_metadata(metadata, paths.state)
    _atomic_write(paths.pid, f"{metadata.pid}\n")
    _atomic_write(paths.port, f"{metadata.port}\n")


def cleanup_runtime_state(paths: RuntimePaths) -> None:
    for path in (paths.pid, paths.port, paths.state):
        path.unlink(missing_ok=True)


def read_metadata(path: Path) -> BackendProcessMetadata:
    try:
        payload = json.loads(path.resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read backend state {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("backend state must be a JSON object")
    return BackendProcessMetadata.from_dict(payload)


def project_python() -> Path:
    import sys
    rel_path = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    candidate = ROOT / "ai_system_env" / rel_path
    if not candidate.is_file():
        parent_candidate = ROOT.parent / "kattappa" / "ai_system_env" / rel_path
        if parent_candidate.is_file():
            return parent_candidate.resolve()
        if Path(sys.executable).is_file():
            return Path(sys.executable).resolve()
        raise RuntimeError(
            f"Kattappa virtual-environment interpreter is missing: {candidate}"
        )
    return candidate.resolve()


def port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def listener_pid_for_port(port: int) -> int | None:
    """Resolve a listener PID without assuming psutil address tuple shape."""
    try:
        connections = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, OSError):
        return None
    for connection in connections:
        if connection.status != psutil.CONN_LISTEN:
            continue
        address = connection.laddr
        address_port = getattr(address, "port", None)
        if address_port is None and isinstance(address, (tuple, list)) and len(address) > 1:
            address_port = address[1]
        if address_port == port:
            return connection.pid
    return None


def process_owns_port(pid: int, port: int) -> bool:
    return listener_pid_for_port(port) == pid


def identity_errors(metadata: BackendProcessMetadata) -> list[str]:
    """Return every reason a live PID is not the recorded Kattappa server."""

    try:
        process = psutil.Process(metadata.pid)
    except psutil.NoSuchProcess:
        return ["process does not exist"]

    errors: list[str] = []
    try:
        if abs(process.create_time() - metadata.started_epoch) > 3.0:
            errors.append("process start timestamp does not match")
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        errors.append("process start timestamp is unavailable")

    try:
        actual_cwd = Path(process.cwd()).resolve()
        if actual_cwd != Path(metadata.cwd).resolve():
            errors.append(f"working directory mismatch: {actual_cwd}")
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
        errors.append("working directory is unavailable")

    try:
        command = " ".join(process.cmdline())
        required = ("uvicorn", "backend.main:app", "--port", str(metadata.port))
        missing = [token for token in required if token not in command]
        if missing:
            errors.append(f"command line is missing: {', '.join(missing)}")
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        errors.append("command line is unavailable")

    if Path(metadata.git_checkout).resolve() != ROOT.resolve():
        errors.append("metadata belongs to a different Git checkout")
    return errors


def terminate_recorded_process(
    metadata: BackendProcessMetadata, *, timeout: float = 10.0
) -> None:
    errors = identity_errors(metadata)
    if errors:
        raise RuntimeError(
            "refusing to terminate PID " + str(metadata.pid) + ": " + "; ".join(errors)
        )
    process = psutil.Process(metadata.pid)
    owned_tree = process.children(recursive=True)
    for child in reversed(owned_tree):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    process.terminate()
    _, alive = psutil.wait_procs([*owned_tree, process], timeout=timeout)
    for remaining in alive:
        try:
            remaining.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=5.0)


def _fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=1.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"endpoint returned non-object JSON: {url}")
    return payload


def wait_for_ready(
    port: int, timeout: float, process: subprocess.Popen[str] | None = None
) -> dict[str, Any]:
    measurement_started = time.perf_counter()
    deadline = measurement_started + timeout
    delay = 0.1
    last_error: BaseException | None = None
    first_health_seconds: float | None = None
    peak_rss_bytes = 0
    while time.perf_counter() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"backend exited during startup with code {process.returncode}")
        try:
            if process is not None:
                try:
                    root_process = psutil.Process(process.pid)
                    family = [root_process, *root_process.children(recursive=True)]
                    peak_rss_bytes = max(
                        peak_rss_bytes,
                        sum(item.memory_info().rss for item in family if item.is_running()),
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            health = _fetch_json(f"http://127.0.0.1:{port}/health")
            if first_health_seconds is None:
                first_health_seconds = time.perf_counter() - measurement_started
            readiness = _fetch_json(f"http://127.0.0.1:{port}/ready")
            if not health.get("status"):
                raise RuntimeError(f"health endpoint is not healthy: {health}")
            if readiness.get("ready") is not True:
                raise RuntimeError(f"readiness endpoint is not ready: {readiness}")
            return {
                **readiness,
                "_startup_metrics": {
                    "health_seconds": round(first_health_seconds, 6),
                    "ready_seconds": round(time.perf_counter() - measurement_started, 6),
                    "peak_rss_bytes": peak_rss_bytes,
                    "heavy_modules_loaded": readiness.get("heavy_modules_loaded", []),
                },
            }
        except (OSError, RuntimeError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(delay)
            delay = min(delay * 1.5, 1.0)
    raise TimeoutError(f"backend did not become ready within {timeout:g}s: {last_error}")


def _log_tail(path: Path, max_chars: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]
    except OSError:
        return "<backend log unavailable>"


def start_backend(
    *,
    port: int,
    metadata_path: Path = DEFAULT_METADATA,
    wait_seconds: float = 30.0,
) -> tuple[BackendProcessMetadata, dict[str, Any]]:
    paths = RuntimePaths.from_metadata(metadata_path)
    paths.state.parent.mkdir(parents=True, exist_ok=True)

    if paths.state.exists():
        existing = read_metadata(paths.state)
        errors = identity_errors(existing)
        if not errors:
            readiness = wait_for_ready(existing.port, wait_seconds)
            return replace(existing, state="running"), readiness
        if errors != ["process does not exist"]:
            raise RuntimeError("unsafe or inconsistent backend state: " + "; ".join(errors))
        cleanup_runtime_state(paths)
    elif paths.pid.exists() or paths.port.exists():
        stale_pid = None
        try:
            stale_pid = int(paths.pid.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pass
        if stale_pid and psutil.pid_exists(stale_pid):
            raise RuntimeError(
                f"orphaned backend PID record points to live PID {stale_pid}; refusing unsafe start"
            )
        cleanup_runtime_state(paths)

    if not port_is_available("127.0.0.1", port):
        raise RuntimeError(
            f"port {port} is occupied; refusing to terminate an unidentified listener"
        )

    argv = [
        str(project_python()),
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    log_handle = paths.log.open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            argv,
            cwd=ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            ),
        )
    finally:
        log_handle.close()

    started_epoch = psutil.Process(process.pid).create_time()
    metadata = BackendProcessMetadata(
        pid=process.pid,
        port=port,
        cwd=str(ROOT.resolve()),
        command=subprocess.list2cmdline(argv),
        argv=argv,
        started_at=datetime.now(timezone.utc).isoformat(),
        started_epoch=started_epoch,
        git_checkout=str(ROOT.resolve()),
        state="starting",
    )
    write_runtime_state(metadata, paths)
    try:
        readiness = wait_for_ready(port, wait_seconds, process)
        listener_pid = listener_pid_for_port(port)
        descendants = {
            child.pid for child in psutil.Process(process.pid).children(recursive=True)
        }
        if listener_pid not in {process.pid, *descendants}:
            raise RuntimeError(
                f"backend became ready but its process tree does not own port {port}"
            )
        if listener_pid != process.pid:
            listener = psutil.Process(listener_pid)
            metadata = replace(
                metadata,
                pid=listener_pid,
                started_epoch=listener.create_time(),
            )
        metadata = replace(metadata, state="running")
        write_runtime_state(metadata, paths)
    except Exception as exc:
        if process.poll() is None:
            terminate_recorded_process(metadata)
        cleanup_runtime_state(paths)
        raise RuntimeError(f"{exc}\nbackend log tail:\n{_log_tail(paths.log)}") from exc
    return metadata, readiness


def stop_backend(
    metadata_path: Path = DEFAULT_METADATA,
) -> BackendProcessMetadata | None:
    paths = RuntimePaths.from_metadata(metadata_path)
    if not paths.state.exists():
        if paths.pid.exists() or paths.port.exists():
            stale_pid = None
            try:
                stale_pid = int(paths.pid.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pass
            if stale_pid and psutil.pid_exists(stale_pid):
                raise RuntimeError(
                    f"cannot identify live PID {stale_pid} without backend state"
                )
        cleanup_runtime_state(paths)
        return None

    metadata = read_metadata(paths.state)
    errors = identity_errors(metadata)
    if errors == ["process does not exist"]:
        cleanup_runtime_state(paths)
        return metadata
    if errors:
        raise RuntimeError("unsafe or inconsistent backend state: " + "; ".join(errors))
    terminate_recorded_process(metadata)
    deadline = time.perf_counter() + 5.0
    while time.perf_counter() < deadline and not port_is_available("127.0.0.1", metadata.port):
        time.sleep(0.1)
    cleanup_runtime_state(paths)
    if not port_is_available("127.0.0.1", metadata.port):
        raise RuntimeError(f"backend stopped but port {metadata.port} was not released")
    return metadata


class DevBackendProcess:
    """Small programmatic facade used by development tooling and tests."""

    def __init__(self, *, port: int = 8000, metadata_path: Path = DEFAULT_METADATA):
        self.port = port
        self.metadata_path = metadata_path

    def is_running(self) -> bool:
        path = self.metadata_path.resolve()
        if not path.exists():
            return False
        try:
            metadata = read_metadata(path)
            return not identity_errors(metadata) and process_owns_port(
                metadata.pid, metadata.port
            )
        except RuntimeError:
            return False

    def start(self, *, wait_seconds: float = 30.0) -> BackendProcessMetadata:
        metadata, _ = start_backend(
            port=self.port,
            metadata_path=self.metadata_path,
            wait_seconds=wait_seconds,
        )
        return metadata

    def stop(self) -> BackendProcessMetadata | None:
        return stop_backend(self.metadata_path)
