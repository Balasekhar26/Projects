"""Shared identity and lifecycle primitives for the development backend."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METADATA = ROOT / ".runtime" / "backend-server.json"


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

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BackendProcessMetadata":
        return cls(**payload)


def write_metadata(metadata: BackendProcessMetadata, path: Path) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(metadata), indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def read_metadata(path: Path) -> BackendProcessMetadata:
    return BackendProcessMetadata.from_dict(
        json.loads(path.resolve().read_text(encoding="utf-8"))
    )


def port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


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
        argv = process.cmdline()
        command = " ".join(argv)
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


def wait_for_ready(port: int, timeout: float) -> dict[str, Any]:
    deadline = time.perf_counter() + timeout
    delay = 0.1
    last_error: Exception | None = None
    while time.perf_counter() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/ready", timeout=1.0
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except OSError as exc:
            last_error = exc
            time.sleep(delay)
            delay = min(delay * 1.5, 1.0)
    raise TimeoutError(f"backend did not become ready: {last_error}")


def start_backend(
    *,
    port: int,
    metadata_path: Path = DEFAULT_METADATA,
    wait_seconds: float = 30.0,
) -> tuple[BackendProcessMetadata, dict[str, Any]]:
    metadata_path = metadata_path.resolve()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    if metadata_path.exists():
        existing = read_metadata(metadata_path)
        errors = identity_errors(existing)
        if not errors:
            raise RuntimeError(
                f"recorded Kattappa backend is already running as PID {existing.pid}"
            )
        if errors != ["process does not exist"]:
            raise RuntimeError(
                "unsafe or inconsistent backend metadata: " + "; ".join(errors)
            )
        metadata_path.unlink()

    if not port_is_available("127.0.0.1", port):
        raise RuntimeError(
            f"port {port} is occupied; refusing to terminate an unidentified listener"
        )

    argv = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    log_path = metadata_path.parent / "backend-server.log"
    log_handle = log_path.open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            argv,
            cwd=ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
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
    )
    write_metadata(metadata, metadata_path)
    try:
        readiness = wait_for_ready(port, wait_seconds)
    except Exception:
        if process.poll() is None:
            terminate_recorded_process(metadata)
        metadata_path.unlink(missing_ok=True)
        raise
    return metadata, readiness


def stop_backend(metadata_path: Path = DEFAULT_METADATA) -> BackendProcessMetadata:
    metadata_path = metadata_path.resolve()
    if not metadata_path.exists():
        raise RuntimeError(f"backend metadata does not exist: {metadata_path}")
    metadata = read_metadata(metadata_path)
    errors = identity_errors(metadata)
    if errors == ["process does not exist"]:
        metadata_path.unlink()
        return metadata
    terminate_recorded_process(metadata)
    metadata_path.unlink(missing_ok=True)
    return metadata
