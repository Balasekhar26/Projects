"""Resource Limiter (Program 20.0).

Determines Docker resource quota constraints per sandbox class to avoid host resource starvation.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ResourceLimiter:
    """Manages Docker runtime limit parameters (RAM, CPU shares, process table constraints)."""

    # Quota specifications mapped per class
    PROFILES: Dict[str, Dict[str, Any]] = {
        "PYTHON": {
            "memory": "512m",
            "cpu_shares": 512,
            "pids_limit": 64
        },
        "BROWSER": {
            "memory": "1024m",
            "cpu_shares": 512,
            "pids_limit": 128
        },
        "FILE": {
            "memory": "256m",
            "cpu_shares": 256,
            "pids_limit": 32
        },
        "BUILD": {
            "memory": "2048m",
            "cpu_shares": 1024,
            "pids_limit": 256
        },
        "RESEARCH": {
            "memory": "256m",
            "cpu_shares": 256,
            "pids_limit": 32
        }
    }

    @classmethod
    def get_docker_flags(cls, sandbox_class: str) -> List[str]:
        """Compiles limits dictionary into Docker engine run arguments."""
        profile = cls.PROFILES.get(sandbox_class.upper(), cls.PROFILES["PYTHON"])
        flags = [
            f"--memory={profile['memory']}",
            f"--cpu-shares={profile['cpu_shares']}",
            f"--pids-limit={profile['pids_limit']}"
        ]
        logger.debug("ResourceLimiter: Configured profile flags for class '%s': %s", sandbox_class, flags)
        return flags
