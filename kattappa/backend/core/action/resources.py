"""Resource telemetry adapters for action results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import psutil


@dataclass(frozen=True, slots=True)
class ResourceMetrics:
    """Point-in-time process resource measurements."""

    cpu_percent: float
    memory_mb: float


class ResourceSamplerProtocol(Protocol):
    """Contract for an injected action resource sampler."""

    def sample(self) -> ResourceMetrics:
        """Return current resource use."""

        ...


class ProcessResourceSampler:
    """Measure the current Kattappa process using psutil."""

    def __init__(self, process: psutil.Process | None = None) -> None:
        self._process = process or psutil.Process()

    def sample(self) -> ResourceMetrics:
        """Return non-blocking CPU utilization and resident memory."""

        return ResourceMetrics(
            cpu_percent=self._process.cpu_percent(interval=None),
            memory_mb=self._process.memory_info().rss / (1024 * 1024),
        )
