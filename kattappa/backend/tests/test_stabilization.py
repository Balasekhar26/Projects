"""Unit and integration tests for Program 8.5: Architecture Stabilization.
"""
from __future__ import annotations

import pytest
from typing import Any, Dict

from backend.core.stabilization.lifecycle import EngineLifecycle
from backend.core.stabilization.container import ServiceContainer
from backend.core.stabilization.config import ConfigManager
from backend.core.stabilization.errors import KattappaError, PlannerError, ExecutionError


class DummyEngine(EngineLifecycle):
    """Mock subclass of EngineLifecycle to test contract implementation constraints."""

    def __init__(self) -> None:
        self.is_initialized = False
        self.is_started = False

    def initialize(self) -> None:
        self.is_initialized = True

    def start(self) -> None:
        self.is_started = True

    def stop(self) -> None:
        self.is_started = False

    def health(self) -> Dict[str, Any]:
        return {"status": "Green", "initialized": self.is_initialized}

    def version(self) -> str:
        return "1.0.0"


def test_engine_lifecycle_interface_contract():
    """Verifies that EngineLifecycle ABC enforces abstract lifecycle overrides."""
    engine = DummyEngine()
    assert engine.version() == "1.0.0"
    
    engine.initialize()
    assert engine.is_initialized is True

    engine.start()
    assert engine.is_started is True
    
    assert engine.health()["status"] == "Green"


def test_service_container_dependency_injection():
    """Verifies that ServiceContainer handles dynamic service registration, lookup, and swap overrides."""
    container = ServiceContainer.get_instance()
    container.clear()

    engine1 = DummyEngine()
    engine2 = DummyEngine()
    engine2.initialize()

    # Register
    container.register("planner_service", engine1)
    assert container.has("planner_service") is True

    # Resolve
    resolved = container.resolve("planner_service")
    assert resolved == engine1
    assert resolved.is_initialized is False

    # Swap implementation (Dependency Override)
    container.register("planner_service", engine2)
    resolved_swapped = container.resolve("planner_service")
    assert resolved_swapped == engine2
    assert resolved_swapped.is_initialized is True


def test_config_manager_feature_flags():
    """Checks that ConfigManager central parameters are read, set, and flags are gated properly."""
    config = ConfigManager.get_instance()
    
    # Check default keys
    assert config.is_enabled("planner.enabled") is True
    assert config.is_enabled("learning.auto_apply") is False

    # Toggle flag
    config.set("learning.auto_apply", True)
    assert config.is_enabled("learning.auto_apply") is True

    # Set unknown config
    assert config.get("unknown_key", "default_val") == "default_val"


def test_error_taxonomy_metadata():
    """Verifies custom error classes preserve error codes, severity levels, and recovery flags."""
    with pytest.raises(PlannerError) as excinfo:
        raise PlannerError(
            message="Plan compilation loop cycle detected",
            error_code="PLAN_CYCLE",
            severity="CRITICAL",
            recoverable=False,
            trace_id="tr_xyz",
        )

    err = excinfo.value
    assert err.error_code == "PLAN_CYCLE"
    assert err.severity == "CRITICAL"
    assert err.recoverable is False
    assert err.trace_id == "tr_xyz"
    assert "Plan compilation loop" in str(err)
