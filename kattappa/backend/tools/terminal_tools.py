from __future__ import annotations

import subprocess
import re
import shlex

from backend.core.config import load_config
from backend.core.safety import classify_risk

SAFE_COMMANDS = {
    ("dir",),
    ("ls",),
    ("pwd",),
    ("python", "--version"),
    ("node", "--version"),
    ("npm", "--version"),
    ("git", "status"),
    ("git", "diff"),
}
SAFE_FIRST_TOKENS = {"pytest", "ruff"}
SHELL_CONTROL_PATTERN = re.compile(r"[;&|<>`]")


def run_command(command: str) -> dict[str, object]:
    config = load_config()
    risk = classify_risk(command)
    if risk.blocked:
        return {"blocked": True, "approval_required": False, "message": risk.reason}
    safe_tokens = _safe_command_tokens(command)
    is_safe = safe_tokens is not None
    if not config.shell_enabled and not is_safe:
        return {
            "approval_required": True,
            "command": command,
            "message": "Shell execution is disabled or command is not allowlisted.",
        }
    if risk.approval_required:
        return {"approval_required": True, "command": command, "message": risk.reason}
    result = subprocess.run(
        safe_tokens if safe_tokens is not None else command,
        shell=safe_tokens is None,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=config.root,
    )
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def _safe_command_tokens(command: str) -> list[str] | None:
    stripped = command.strip()
    if not stripped or SHELL_CONTROL_PATTERN.search(stripped):
        return None
    try:
        tokens = shlex.split(stripped, posix=False)
    except ValueError:
        return None
    if not tokens:
        return None
    normalized = tuple(token.lower() for token in tokens)
    if normalized in SAFE_COMMANDS:
        return tokens
    if normalized[0] in SAFE_FIRST_TOKENS:
        return tokens
    return None
