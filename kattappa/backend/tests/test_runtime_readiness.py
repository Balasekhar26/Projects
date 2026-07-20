from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
import psutil

ROOT = Path(__file__).resolve().parents[2]


def unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def fetch_json(url: str, timeout: float = 1.0) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def stop_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    root = psutil.Process(process.pid)
    descendants = root.children(recursive=True)
    for child in reversed(descendants):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    root.terminate()
    _, alive = psutil.wait_procs([*descendants, root], timeout=10)
    for remaining in alive:
        try:
            remaining.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=5)


@pytest.mark.unit
def test_readiness_probe_does_not_import_torch() -> None:
    code = (
        "import sys; "
        "from backend.core.readiness import runtime_readiness; "
        "result = runtime_readiness(); "
        "assert result.finance_brain.execution_enabled is False; "
        "assert 'torch' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration
@pytest.mark.slow
def test_backend_subprocess_reaches_readiness_within_30_seconds() -> None:
    port = unused_local_port()
    environment = os.environ.copy()
    environment["KATTAPPA_TEST_MODE"] = "false"
    started = time.perf_counter()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload: dict[str, object] | None = None
    try:
        deadline = started + 30.0
        delay = 0.1
        while time.perf_counter() < deadline:
            if process.poll() is not None:
                break
            try:
                payload = fetch_json(f"http://127.0.0.1:{port}/ready")
                break
            except OSError:
                time.sleep(delay)
                delay = min(delay * 1.5, 1.0)

        if payload is None:
            stop_process_tree(process)
            stdout, stderr = process.communicate(timeout=10)
            pytest.fail(
                "backend did not become ready within 30 seconds\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            )

        assert payload == {
            "status": "ready",
            "ready": True,
            "finance_brain": {
                "available": True,
                "source": "vendored",
                "execution_enabled": False,
            },
        }
    finally:
        stop_process_tree(process)
