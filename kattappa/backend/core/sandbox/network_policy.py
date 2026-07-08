"""Network Policy (Program 20.0).

Sets network isolation boundaries (bridge vs none network mappings) for container instances.
"""
from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger(__name__)


class NetworkPolicy:
    """Manages container network isolation policies."""

    @classmethod
    def get_network_flags(cls, sandbox_class: str) -> List[str]:
        """Resolves network options.

        Python, Build, and File sandboxes are strictly offline (--network none).
        Browser and Research classes allow network connections (--network bridge).
        """
        sandbox_upper = sandbox_class.upper()
        
        if sandbox_upper in ("BROWSER", "RESEARCH"):
            logger.debug("NetworkPolicy: Enabled bridge interface for class '%s'", sandbox_class)
            return ["--network", "bridge"]

        logger.debug("NetworkPolicy: Offline isolation forced for class '%s'", sandbox_class)
        return ["--network", "none"]
