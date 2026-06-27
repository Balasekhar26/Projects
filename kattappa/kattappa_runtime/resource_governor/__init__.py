"""
Kattappa Resource Governor (KRG) — Step 30
==========================================

First-class resource monitoring, safety protection, budgeting, throttling, routing, and compression layer.
"""

from kattappa_runtime.resource_governor.engine import ResourceGovernorEngine
from kattappa_runtime.resource_governor.safety_controller import SafetyController
from kattappa_runtime.resource_governor.schema import (
    AppleSiliconPressure,
    ApprovalResult,
    GovernanceConfig,
    SafetyThresholds,
    SafetyVerdict,
    SubsystemBudget,
    SubsystemStats,
    SystemResourceMetrics,
    TrainerBudget,
    TrainingConfig,
)

__all__ = [
    "GovernanceConfig",
    "SubsystemBudget",
    "SystemResourceMetrics",
    "SubsystemStats",
    "ResourceGovernorEngine",
    "SafetyController",
    "AppleSiliconPressure",
    "SafetyThresholds",
    "TrainerBudget",
    "TrainingConfig",
    "SafetyVerdict",
    "ApprovalResult",
]
