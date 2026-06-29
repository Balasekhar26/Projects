"""Centralized Configuration and Feature Flags Management (Program 8.5).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages active system variables configurations and experimental feature gates."""

    _instance: Optional[ConfigManager] = None

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {
            "planner.enabled": True,
            "planner.parallel_layers": True,
            "execution.retry_limit": 3,
            "reflection.enabled": True,
            "learning.auto_apply": False,
            "telemetry.enabled": True,
        }

    @classmethod
    def get_instance(cls) -> ConfigManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._config[key] = value
        logger.debug("Config parameter updated: %s = %s", key, value)

    def is_enabled(self, feature_flag: str) -> bool:
        """Helper returns boolean status of feature flag gates."""
        val = self._config.get(feature_flag, False)
        return bool(val)

    def export_all(self) -> Dict[str, Any]:
        return dict(self._config)
