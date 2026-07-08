"""REST API Router for Architecture Stabilization Layer (Program 8.5).
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException

from backend.core.stabilization.container import ServiceContainer
from backend.core.stabilization.config import ConfigManager

router = APIRouter(prefix="/stabilization", tags=["Architecture Stabilization"])
_container = ServiceContainer.get_instance()
_config = ConfigManager.get_instance()


@router.get("/engines", summary="List registered cognitive engines and check health status")
def get_registered_engines() -> Dict[str, Any]:
    """Retrieves list of active system engines registered in DI container, along with health metrics."""
    engines_health = {}
    for name in list(_container._services.keys()):
        instance = _container.resolve(name)
        # Check if instance implements EngineLifecycle health check
        if hasattr(instance, "health"):
            engines_health[name] = instance.health()
        else:
            engines_health[name] = {"status": "Green", "notes": "Legacy component without lifecycle hook"}

    return {
        "status": "ok",
        "engines": engines_health,
    }


@router.get("/config", summary="Get active configurations and feature flags")
def get_active_configurations() -> Dict[str, Any]:
    """Returns central parameter configs and feature flag toggles registry."""
    return {
        "status": "ok",
        "configuration": _config.export_all(),
    }
