"""Start the Kattappa development backend with PID identity metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _backend_process import DEFAULT_METADATA, start_backend


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--port", type=int, default=8000)
    result.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    result.add_argument("--wait-seconds", type=float, default=30.0)
    return result


def main() -> int:
    args = parser().parse_args()
    metadata, readiness = start_backend(
        port=args.port,
        metadata_path=args.metadata,
        wait_seconds=args.wait_seconds,
    )
    print(
        json.dumps(
            {"pid": metadata.pid, "port": metadata.port, "readiness": readiness},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
