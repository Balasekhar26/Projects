"""Container Pool (Program 20.0).

Pre-pulls and manages reusable warm Docker images to optimize container cold-start speeds.
"""
from __future__ import annotations

import logging
import subprocess
import threading
from typing import Dict, Set

logger = logging.getLogger(__name__)


class ContainerPool:
    """Pre-pulls and tracks cached Docker image lifecycles to reduce latency."""

    _pulled_images: Set[str] = set()
    _lock = threading.Lock()

    @classmethod
    def pre_pull_image(cls, image: str) -> None:
        """Pre-pulls the specified Docker image in a background thread."""
        with cls._lock:
            if image in cls._pulled_images:
                return

        def run_pull():
            try:
                logger.info("ContainerPool: Pulling image '%s' in background...", image)
                res = subprocess.run(["docker", "pull", image], capture_output=True, timeout=120.0)
                if res.returncode == 0:
                    with cls._lock:
                        cls._pulled_images.add(image)
                    logger.info("ContainerPool: Successfully pulled image '%s'", image)
                else:
                    logger.warning("ContainerPool: Failed to pull image '%s': %s", image, res.stderr)
            except Exception as e:
                logger.debug("ContainerPool: Background pull failed for '%s' — %s", image, e)

        thread = threading.Thread(target=run_pull, daemon=True)
        thread.start()

    @classmethod
    def is_cached(cls, image: str) -> bool:
        with cls._lock:
            return image in cls._pulled_images
