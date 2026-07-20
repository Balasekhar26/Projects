"""Verify that Kattappa imports resolve only from the active workspace."""

from __future__ import annotations

import json

from environment_guard import verify_environment


def main() -> int:
    report = verify_environment()
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
