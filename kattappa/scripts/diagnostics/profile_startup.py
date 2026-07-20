"""Measure Kattappa import, bind, readiness, and memory timing."""

from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "artifacts" / "diagnostics" / "startup-profile.json"


def unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def import_timings(timeout: float) -> dict[str, float]:
    code = """
import importlib, json, time
started = time.perf_counter()
importlib.import_module('backend.main')
cold = time.perf_counter() - started
started = time.perf_counter()
importlib.import_module('backend.main')
warm = time.perf_counter() - started
print(json.dumps({'cold_import_seconds': cold, 'warm_import_seconds': warm}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env={**os.environ, "KATTAPPA_TEST_MODE": "false"},
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    for line in reversed(result.stdout.splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise RuntimeError("import timing subprocess produced no JSON")


def server_timings(timeout: float) -> dict[str, float]:
    port = unused_port()
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
        env={**os.environ, "KATTAPPA_TEST_MODE": "false"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    started = time.perf_counter()
    bound_at: float | None = None
    ready_at: float | None = None
    try:
        deadline = started + timeout
        while time.perf_counter() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"backend exited with code {process.returncode}")
            if bound_at is None:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        bound_at = time.perf_counter()
                except OSError:
                    pass
            if bound_at is not None:
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/ready", timeout=0.5
                    ) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    if payload.get("ready") is True:
                        ready_at = time.perf_counter()
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        if bound_at is None or ready_at is None:
            raise TimeoutError(f"backend did not become ready within {timeout} seconds")
        rss = psutil.Process(process.pid).memory_info().rss / (1024**2)
        return {
            "socket_bind_seconds": bound_at - started,
            "ready_seconds": ready_at - started,
            "rss_mb_after_readiness": rss,
        }
    finally:
        if process.poll() is None:
            root = psutil.Process(process.pid)
            tree = root.children(recursive=True)
            for member in reversed([*tree, root]):
                try:
                    member.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs([*tree, root], timeout=10)
            for member in alive:
                try:
                    member.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(alive, timeout=5)


def summary(values: list[float]) -> dict[str, float]:
    return {
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
        "standard_deviation": statistics.pstdev(values),
    }


def profile(runs: int, timeout: float) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for run in range(1, runs + 1):
        sample: dict[str, Any] = {"run": run}
        try:
            sample.update(import_timings(timeout))
            sample.update(server_timings(timeout))
            sample["success"] = True
        except Exception as exc:
            sample["success"] = False
            sample["error"] = f"{type(exc).__name__}: {exc}"
        samples.append(sample)
    metric_names = (
        "cold_import_seconds",
        "warm_import_seconds",
        "socket_bind_seconds",
        "ready_seconds",
        "rss_mb_after_readiness",
    )
    successful = [sample for sample in samples if sample["success"]]
    return {
        "runs": runs,
        "successful_runs": len(successful),
        "samples": samples,
        "summary": {
            metric: summary([sample[metric] for sample in successful])
            for metric in metric_names
            if successful
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--runs", type=int, default=5)
    result.add_argument("--timeout", type=float, default=120.0)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be positive")
    report = profile(args.runs, args.timeout)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"runs": args.runs, "output": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
