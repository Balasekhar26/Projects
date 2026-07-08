"""Dependency Injection Service Container (Program 8.5).

Coordinates component registrations, resolutions, and mock swapping.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Type

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Registry container facilitating decoupled dependency injection swaps."""

    _instance: Optional[ServiceContainer] = None

    def __init__(self) -> None:
        self._services: Dict[str, Any] = {}

    @classmethod
    def get_instance(cls) -> ServiceContainer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, service_name: str, instance: Any) -> None:
        """Registers a service instance to the container."""
        self._services[service_name] = instance
        logger.info("Registered service in container: %s", service_name)

    def resolve(self, service_name: str) -> Any:
        """Retrieves registered service instance, raising KeyError if missing."""
        if service_name not in self._services:
            raise KeyError(f"Service '{service_name}' not registered in container.")
        return self._services[service_name]

    def has(self, service_name: str) -> bool:
        return service_name in self._services

    def clear(self) -> None:
        self._services.clear()
