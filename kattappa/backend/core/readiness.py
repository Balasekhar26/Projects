"""Canonical, side-effect-free runtime readiness contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from backend.core.semantic_cache import SemanticResponseCache
from backend.tools.finance_brain import kronos_status


class FinanceReadiness(BaseModel):
    available: bool
    source: Literal["vendored", "external", "unavailable"]
    execution_enabled: bool = False


class SemanticCacheReadiness(BaseModel):
    available: bool
    semantic_available: bool
    mode: Literal[
        "semantic", "exact_match_fallback", "exact_match_with_lazy_semantic"
    ]
    reason: str | None = None


class RuntimeReadiness(BaseModel):
    status: Literal["ready", "degraded", "not_ready"]
    ready: bool
    finance_brain: FinanceReadiness
    semantic_cache: SemanticCacheReadiness


def runtime_readiness() -> RuntimeReadiness:
    """Inspect availability without importing or loading forecasting models."""

    finance_status = kronos_status()
    cache_status = SemanticResponseCache.health()
    return RuntimeReadiness(
        status="ready",
        ready=True,
        finance_brain=FinanceReadiness(
            available=bool(finance_status["installed"]),
            source=finance_status["source"],
            execution_enabled=False,
        ),
        semantic_cache=SemanticCacheReadiness(
            available=bool(cache_status["available"]),
            semantic_available=bool(cache_status["semantic_available"]),
            mode=cache_status["mode"],
            reason=cache_status["reason"],
        ),
    )
