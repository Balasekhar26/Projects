from __future__ import annotations

import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import psutil
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from _backend_process import (  # noqa: E402
    BackendProcessMetadata,
    identity_errors,
    port_is_available,
    terminate_recorded_process,
    write_metadata,
)

pytestmark = [pytest.mark.unit, pytest.mark.safety]


def test_occupied_port_is_detected_without_terminating_listener() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = int(listener.getsockname()[1])
        assert port_is_available("127.0.0.1", port) is False
        assert listener.fileno() >= 0


def test_termination_refuses_mismatched_process_identity() -> None:
    process = psutil.Process(os.getpid())
    metadata = BackendProcessMetadata(
        pid=process.pid,
        port=8000,
        cwd=str(ROOT),
        command="not-kattappa",
        argv=["not-kattappa"],
        started_at=datetime.now(timezone.utc).isoformat(),
        started_epoch=process.create_time(),
        git_checkout=str(ROOT),
    )

    errors = identity_errors(metadata)
    assert any("command line is missing" in error for error in errors)
    with pytest.raises(RuntimeError, match="refusing to terminate"):
        terminate_recorded_process(metadata)
    assert psutil.pid_exists(os.getpid())


def test_metadata_writer_creates_runtime_directory(tmp_path: Path) -> None:
    process = psutil.Process(os.getpid())
    metadata = BackendProcessMetadata(
        pid=process.pid,
        port=8000,
        cwd=str(ROOT),
        command="test",
        argv=["test"],
        started_at=datetime.now(timezone.utc).isoformat(),
        started_epoch=process.create_time(),
        git_checkout=str(ROOT),
    )
    path = tmp_path / "nested" / "backend-server.json"
    write_metadata(metadata, path)
    assert path.exists()
