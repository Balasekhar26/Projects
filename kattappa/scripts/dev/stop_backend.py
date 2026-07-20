"""Stop only the Kattappa backend identified by recorded PID metadata."""

from __future__ import annotations

import argparse
from pathlib import Path

from _backend_process import DEFAULT_METADATA, stop_backend


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    return result


def main() -> int:
    args = parser().parse_args()
    metadata = stop_backend(args.metadata)
    if metadata is None:
        print("Kattappa backend is already stopped")
    else:
        print(f"Stopped recorded Kattappa backend PID {metadata.pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
