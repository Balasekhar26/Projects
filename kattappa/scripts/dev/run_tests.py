"""Hermetic Kattappa pytest entry point."""

from __future__ import annotations

import sys

from environment_guard import require_verified_environment


def main() -> int:
    require_verified_environment()
    import pytest

    return int(pytest.main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
