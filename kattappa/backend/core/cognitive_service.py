"""Dependency-neutral cognitive service lifecycle contracts.

Keeping these contracts outside the kernel prevents managed services from
having to import the kernel module while its global singleton is being built.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from backend.core.cognitive_kernel import CognitiveKernel


class ServiceStatus:
    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    DEGRADED = "degraded"
    FAILED = "failed"
    SHUTTING_DOWN = "shutting_down"


class CognitiveService:
    """Base class for subsystems managed by :class:`CognitiveKernel`."""

    def __init__(self, name: str, dependencies: Optional[List[str]] = None) -> None:
        self._name = name
        self._dependencies = dependencies or []
        self._status = ServiceStatus.INACTIVE
        self._error: Optional[str] = None
        self._kernel: Optional["CognitiveKernel"] = None
        self._last_health_check_time: float = 0.0

    @property
    def name(self) -> str:
        return self._name

    @property
    def dependencies(self) -> List[str]:
        return self._dependencies

    @property
    def status(self) -> str:
        return self._status

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def kernel(self) -> "CognitiveKernel":
        if self._kernel is None:
            raise RuntimeError(f"Service {self._name!r} has not been registered with a kernel.")
        return self._kernel

    def set_status(self, status: str, error: Optional[str] = None) -> None:
        self._status = status
        self._error = error

    def set_kernel(self, kernel: "CognitiveKernel") -> None:
        self._kernel = kernel

    def initialize(self) -> None:
        """Lifecycle hook called during kernel start or registration."""
        self.set_status(ServiceStatus.ACTIVE)

    def shutdown(self) -> None:
        """Lifecycle hook called during kernel shutdown or deregistration."""
        self.set_status(ServiceStatus.INACTIVE)

    def health_check(self) -> Dict[str, Any]:
        """Evaluate and report the service lifecycle state."""
        self._last_health_check_time = time.time()
        return {
            "status": self._status,
            "error": self._error,
            "healthy": self._status in (ServiceStatus.ACTIVE, ServiceStatus.INACTIVE),
            "timestamp": self._last_health_check_time,
        }
