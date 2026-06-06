from __future__ import annotations

import subprocess
from dataclasses import dataclass

from ai_system.core.config import Settings


@dataclass
class ShellTool:
    settings: Settings

    def run(self, command: str, timeout: int = 60) -> str:
        if not self.settings.allow_shell:
            return "Shell execution is disabled. Set AI_SYSTEM_ALLOW_SHELL=true in .env to enable it."
        completed = subprocess.run(
            command,
            cwd=self.settings.root,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        output = completed.stdout.strip()
        error = completed.stderr.strip()
        if completed.returncode != 0:
            return f"Command failed with exit code {completed.returncode}\n{error or output}"
        return output or error or "Command completed with no output."
