"""Observation Layer (Layer 1).

Parses text, active workspace files, cursor state, system datetime, platform OS,
and environment configuration under 10 ms.
"""

from __future__ import annotations

import datetime
import platform
from typing import Any, Dict, Optional

from backend.core.config import load_config
from backend.core.memory import get_git_status


class Observer:
    @classmethod
    def observe(
        cls,
        raw_message: str,
        session_id: str,
        active_document: Optional[Dict[str, Any]] = None,
        current_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Gathers runtime metadata and builds the initial observation frame."""
        now = datetime.datetime.now()
        time_str = now.strftime("%I:%M %p")
        date_str = now.strftime("%Y-%m-%d (%A)")
        os_platform = platform.system()

        if not active_document:
            active_document = {
                "filepath": None,
                "cursor_line": 0,
                "language": None,
            }

        config = load_config()
        workspace_dir = str(config.workspace_dir)

        # Retrieve git status (utilizes memory.py cached subprocess call)
        git_status = get_git_status()

        workspace_metadata = {
            "workspace_dir": workspace_dir,
            "git_status": git_status,
        }

        return {
            "raw_message": raw_message,
            "session_id": session_id,
            "system_time": time_str,
            "system_date": date_str,
            "os_platform": os_platform,
            "active_document": active_document,
            "workspace_metadata": workspace_metadata,
            "current_message_id": current_message_id,
        }
