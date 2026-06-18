from __future__ import annotations

from backend.tools.terminal_tools import run_command


def git_status() -> dict[str, object]:
    return run_command("git status --short")


def run_tests() -> dict[str, object]:
    import platform
    python_path = ".\\ai_system_env\\Scripts\\python.exe" if platform.system().lower() == "windows" else "./ai_system_env/bin/python"
    return run_command(f"{python_path} -m pytest tests -q")
