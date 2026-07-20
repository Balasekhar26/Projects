"""Canonical, side-effect-free runtime readiness contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from backend.tools.finance_brain import kronos_status


class FinanceReadiness(BaseModel):
    available: bool
    source: Literal["vendored", "external", "unavailable"]
    execution_enabled: bool = False


class RuntimeReadiness(BaseModel):
    status: Literal["ready", "degraded", "not_ready"]
    ready: bool
    finance_brain: FinanceReadiness


def runtime_readiness() -> RuntimeReadiness:
    """Inspect availability without importing or loading forecasting models."""

    finance_status = kronos_status()
    return RuntimeReadiness(
        status="ready",
        ready=True,
        finance_brain=FinanceReadiness(
            available=bool(finance_status["installed"]),
            source=finance_status["source"],
            execution_enabled=False,
        ),
    )
