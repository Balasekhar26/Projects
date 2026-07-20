"""Validation-only foreground wrapper for process-sandbox environments."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV_SCRIPTS = ROOT / "scripts" / "dev"
sys.path.insert(0, str(DEV_SCRIPTS))

from _backend_process import DEFAULT_METADATA, start_backend, stop_backend  # noqa: E402
from environment_guard import require_verified_environment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--wait-seconds", type=float, default=30.0)
    args = parser.parse_args()
    require_verified_environment()
    metadata, readiness = start_backend(
        port=args.port,
        metadata_path=args.metadata,
        wait_seconds=args.wait_seconds,
    )
    print(json.dumps({"pid": metadata.pid, "readiness": readiness}, indent=2))
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        stop_backend(args.metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
