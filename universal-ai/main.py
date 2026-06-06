from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run_backend() -> int:
    return subprocess.call(
        [
            str(ROOT / "ai_system_env" / "Scripts" / "python.exe"),
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=ROOT,
    )


def run_cli() -> int:
    return subprocess.call([str(ROOT / "ai_system_env" / "Scripts" / "python.exe"), "-m", "ai_system.cli", "chat"], cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kattappa AI OS launcher")
    parser.add_argument("--mode", choices=["backend", "cli"], default="backend")
    args = parser.parse_args()
    if args.mode == "cli":
        return run_cli()
    return run_backend()


if __name__ == "__main__":
    sys.exit(main())
