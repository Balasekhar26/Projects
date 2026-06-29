"""Unified Subsystem Lifecycle Contract Interface (Program 8.5).

Abstract Base Class enforcing consistent lifecycle hooks on all cognitive modules.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class EngineLifecycle(ABC):
    """Enforces standard runtime hooks across cognitive engines."""

    @abstractmethod
    def initialize(self) -> None:
        """Initializes internal configurations and database contexts."""
        pass

    @abstractmethod
    def start(self) -> None:
        """Triggers startup connections, thread listeners, or schedulers."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stops active processes and cleans allocated resources."""
        pass

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Returns diagnostic health metrics (status: Green/Yellow/Red, timings)."""
        pass

    @abstractmethod
    def version(self) -> str:
        """Returns current semantic version of the component."""
        pass
