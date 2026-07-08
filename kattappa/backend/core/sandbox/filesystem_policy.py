"""Filesystem Policy (Program 20.0).

Enforces filesystem access limits (Read-Only vs Read-Write volume mappings) for Docker execution pools.
"""
from __future__ import annotations

import logging
import os
from typing import List

logger = logging.getLogger(__name__)


class FilesystemPolicy:
    """Manages workspace mounting directories and write permissions."""

    @classmethod
    def get_mount_flags(cls, sandbox_class: str, is_mutating: bool, host_ws_dir: str) -> List[str]:
        """Resolves workspace volume mount parameters.

        Browser and Research classes are strictly mapped read-only (:ro).
        Build, File, and Python containers can map read-write (:rw) when mutating actions are run.
        """
        sandbox_upper = sandbox_class.upper()
        mode = "ro"

        # Mutating checks
        if sandbox_upper in ("PYTHON", "BUILD", "FILE") and is_mutating:
            mode = "rw"

        # Explicitly force read-only for research/browser
        if sandbox_upper in ("BROWSER", "RESEARCH"):
            mode = "ro"

        mount_flags = ["-v", f"{host_ws_dir}:/workspace:{mode}"]
        logger.debug("FilesystemPolicy: Class '%s' configured with mode '%s'", sandbox_class, mode)
        return mount_flags
