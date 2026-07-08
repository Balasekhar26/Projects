"""Artifact Exporter (Program 20.0).

Verifies and manages export of outputs and generated files out of container environments.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Dict

logger = logging.getLogger(__name__)


class ArtifactExporter:
    """Synchronizes output files and reports generated inside temporary container scopes."""

    @classmethod
    def export_container_file(
        cls,
        container_id: str,
        container_path: str,
        host_destination: str
    ) -> bool:
        """Copies file out of active container namespace to the host path."""
        try:
            cmd = ["docker", "cp", f"{container_id}:{container_path}", host_destination]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10.0)
            if res.returncode == 0:
                logger.info("ArtifactExporter: Successfully copied %s to %s", container_path, host_destination)
                return True
            logger.error("ArtifactExporter: cp failed: %s", res.stderr)
        except Exception as e:
            logger.error("ArtifactExporter: Failed copy execution — %s", e)
        return False
