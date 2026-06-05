from __future__ import annotations

from backend.tools.terminal_tools import run_command


def git_status() -> dict[str, object]:
    return run_command("git status --short")


def run_tests() -> dict[str, object]:
    return run_command(".\\ai_system_env\\Scripts\\python.exe -m pytest tests -q")
