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
    DevBackendProcess,
    RuntimePaths,
    cleanup_runtime_state,
    identity_errors,
    port_is_available,
    project_python,
    read_metadata,
    stop_backend,
    terminate_recorded_process,
    write_metadata,
    write_runtime_state,
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


def test_runtime_state_writes_pid_port_and_json_atomically(tmp_path: Path) -> None:
    process = psutil.Process(os.getpid())
    metadata = BackendProcessMetadata(
        pid=process.pid,
        port=8123,
        cwd=str(ROOT),
        command="test",
        argv=["test"],
        started_at=datetime.now(timezone.utc).isoformat(),
        started_epoch=process.create_time(),
        git_checkout=str(ROOT),
    )
    paths = RuntimePaths.from_metadata(tmp_path / "backend.state.json")
    write_runtime_state(metadata, paths)

    assert paths.pid.read_text(encoding="utf-8").strip() == str(process.pid)
    assert paths.port.read_text(encoding="utf-8").strip() == "8123"
    assert read_metadata(paths.state) == metadata
    cleanup_runtime_state(paths)
    assert not any(path.exists() for path in (paths.pid, paths.port, paths.state))


def test_malformed_list_state_has_clear_contract_error(tmp_path: Path) -> None:
    state = tmp_path / "backend.state.json"
    state.write_text("[]", encoding="utf-8")
    with pytest.raises(RuntimeError, match="JSON object"):
        read_metadata(state)


def test_stop_is_idempotent_and_cleans_stale_files(tmp_path: Path) -> None:
    paths = RuntimePaths.from_metadata(tmp_path / "backend.state.json")
    paths.state.parent.mkdir(parents=True, exist_ok=True)
    paths.pid.write_text("99999999\n", encoding="utf-8")
    paths.port.write_text("8123\n", encoding="utf-8")

    assert stop_backend(paths.state) is None
    assert stop_backend(paths.state) is None
    assert not paths.pid.exists()
    assert not paths.port.exists()


def test_launcher_uses_project_virtual_environment() -> None:
    assert sys.prefix != sys.base_prefix
    interpreter = project_python()
    assert interpreter.is_file()
    parent_names = [p.name for p in interpreter.parents]
    assert any(name in parent_names for name in ("ai_system_env", "k-r0.5-py310", Path(sys.prefix).name))


@pytest.mark.integration
@pytest.mark.slow
def test_dev_backend_process_start_repeat_stop_cycle(tmp_path: Path) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])

    state = tmp_path / "backend.state.json"
    manager = DevBackendProcess(port=port, metadata_path=state)
    paths = RuntimePaths.from_metadata(state)
    try:
        first = manager.start(wait_seconds=30.0)
        assert manager.is_running()
        assert first.state == "running"
        assert all(path.exists() for path in (paths.state, paths.pid, paths.port))

        second = manager.start(wait_seconds=5.0)
        assert second.pid == first.pid

        stopped = manager.stop()
        assert stopped is not None
        assert stopped.pid == first.pid
        assert manager.is_running() is False
        assert not any(path.exists() for path in (paths.state, paths.pid, paths.port))
        assert manager.stop() is None
    finally:
        if manager.is_running():
            manager.stop()
