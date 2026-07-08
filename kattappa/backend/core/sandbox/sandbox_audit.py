"""Sandbox Audit (Program 20.0).

Handles logging and telemetry for container sandboxed command runs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

SANDBOX_RUN = "SandboxRun"


def _publish(event_name: str, payload: Dict[str, Any]) -> None:
    try:
        from backend.core.event_bus import EVENT_BUS
        EVENT_BUS.publish(event_name, payload=payload, source="core.sandbox")
    except Exception as exc:
        logger.debug("SandboxAudit: could not publish %s — %s", event_name, exc)


class SandboxAudit:
    """Emits container execution parameters and resource telemetry to the event ledger."""

    @classmethod
    def record_run(
        cls,
        sandbox_class: str,
        cmd: List[str],
        exit_code: int,
        duration_ms: int,
        limits: Dict[str, Any]
    ) -> None:
        """Sanitizes sensitive arguments and logs container run metadata."""
        # Sanitize command strings to prevent secret leakages
        sanitized_cmd = []
        secret_patterns = ["key", "token", "password", "secret", "auth"]
        
        for arg in cmd:
            if any(pat in arg.lower() for pat in secret_patterns) and "=" in arg:
                parts = arg.split("=", 1)
                sanitized_cmd.append(f"{parts[0]}=********")
            else:
                sanitized_cmd.append(arg)

        logger.info(
            "SandboxAudit: Class '%s' executed command %s (exit: %d, time: %dms)",
            sandbox_class, sanitized_cmd, exit_code, duration_ms
        )

        _publish(SANDBOX_RUN, {
            "sandbox_class": sandbox_class,
            "cmd": sanitized_cmd,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "limits": limits
        })
