"""Measure ten or more clean Kattappa backend cold starts."""

from __future__ import annotations

import argparse
import json
import socket
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev"
sys.path.insert(0, str(DEV))

from _backend_process import start_backend, stop_backend  # noqa: E402
from environment_guard import require_verified_environment  # noqa: E402


def _port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * percentile) + 0.999999) - 1))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs" / "evidence" / "backend_startup_measurements.json",
    )
    args = parser.parse_args()
    if args.runs < 10:
        parser.error("at least 10 runs are required")
    require_verified_environment()

    measurements: list[dict[str, object]] = []
    runtime_dir = ROOT / ".kattappa" / "validation" / "startup"
    for index in range(args.runs):
        state = runtime_dir / f"run-{index + 1}" / "backend.state.json"
        port = _port()
        try:
            metadata, readiness = start_backend(
                port=port,
                metadata_path=state,
                wait_seconds=args.timeout,
            )
            metrics = dict(readiness["_startup_metrics"])
            metrics.update({"run": index + 1, "pid": metadata.pid, "port": port})
            measurements.append(metrics)
        finally:
            stop_backend(state)

    ready_values = [float(item["ready_seconds"]) for item in measurements]
    health_values = [float(item["health_seconds"]) for item in measurements]
    report = {
        "runs": measurements,
        "summary": {
            "health_min_seconds": min(health_values),
            "health_median_seconds": statistics.median(health_values),
            "health_p95_seconds": _percentile(health_values, 0.95),
            "health_max_seconds": max(health_values),
            "ready_min_seconds": min(ready_values),
            "ready_median_seconds": statistics.median(ready_values),
            "ready_p95_seconds": _percentile(ready_values, 0.95),
            "ready_max_seconds": max(ready_values),
            "peak_rss_bytes": max(int(item["peak_rss_bytes"]) for item in measurements),
            "heavy_modules_loaded": sorted(
                {
                    module
                    for item in measurements
                    for module in item.get("heavy_modules_loaded", [])
                }
            ),
            "timeout_seconds": args.timeout,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
