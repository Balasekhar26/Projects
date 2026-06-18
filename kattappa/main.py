from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _venv_python() -> Path:
    if platform.system().lower() == "windows":
        return ROOT / "ai_system_env" / "Scripts" / "python.exe"
    return ROOT / "ai_system_env" / "bin" / "python"


def run_backend() -> int:
    return subprocess.call(
        [
            str(_venv_python()),
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
    return subprocess.call([str(_venv_python()), "-m", "ai_system.cli", "chat"], cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kattappa AI OS launcher")
    parser.add_argument("--mode", choices=["backend", "cli"], default="backend")
    args = parser.parse_args()
    if args.mode == "cli":
        return run_cli()
    return run_backend()


if __name__ == "__main__":
    sys.exit(main())
