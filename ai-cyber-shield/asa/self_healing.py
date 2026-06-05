from __future__ import annotations

import getpass
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from .config import ASAConfig
from .models import ActionResult

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None


class SelfHealingEngine:
    def __init__(self, config: ASAConfig) -> None:
        self.config = config
        self.config.ensure_dirs()

    def terminate_process(self, pid: int, dry_run: bool = True) -> ActionResult:
        process_name = self._process_name(pid)
        if not process_name:
            return ActionResult("terminate_process", False, "Process is not visible", {"pid": pid})
        if process_name in self.config.protected_process_names:
            return ActionResult(
                "terminate_process",
                False,
                "Refused to terminate protected process",
                {"pid": pid, "process_name": process_name},
            )
        if not self._owned_by_current_user(pid):
            return ActionResult(
                "terminate_process",
                False,
                "Refused to terminate process owned by another user",
                {"pid": pid, "process_name": process_name},
            )
        if dry_run:
            return ActionResult(
                "terminate_process",
                True,
                "Dry run: process would be terminated",
                {"pid": pid, "process_name": process_name},
            )

        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
        except ProcessLookupError:
            return ActionResult("terminate_process", True, "Process already stopped", {"pid": pid})
        except PermissionError:
            return ActionResult("terminate_process", False, "Permission denied", {"pid": pid})

        return ActionResult(
            "terminate_process",
            True,
            "TERM signal sent to suspicious process",
            {"pid": pid, "process_name": process_name},
        )

    def quarantine_file(self, path: Path, dry_run: bool = True) -> ActionResult:
        target = path.expanduser().resolve()
        if not target.exists() or not target.is_file():
            return ActionResult("quarantine_file", False, "File is not visible", {"path": str(path)})
        if dry_run:
            return ActionResult(
                "quarantine_file",
                True,
                "Dry run: file would be moved to quarantine",
                {"path": str(target)},
            )
        destination = self.config.quarantine_dir / f"{int(time.time())}-{target.name}"
        shutil.move(str(target), destination)
        return ActionResult(
            "quarantine_file",
            True,
            "File moved to local quarantine",
            {"source": str(target), "destination": str(destination)},
        )

    def _process_name(self, pid: int) -> str:
        if psutil is not None:
            try:
                return str(psutil.Process(pid).name())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return ""
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True,
            text=True,
            check=False,
        )
        return Path(result.stdout.strip()).name

    def _owned_by_current_user(self, pid: int) -> bool:
        if psutil is None:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "user="],
                capture_output=True,
                text=True,
                check=False,
            )
            owner = result.stdout.strip().split(None, 1)[0] if result.stdout.strip() else ""
            return owner == getpass.getuser()
        try:
            current = psutil.Process(os.getpid()).username()
            owner = psutil.Process(pid).username()
            return current == owner
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
