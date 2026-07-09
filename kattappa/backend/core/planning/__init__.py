"""Kattappa Planning and Execution Reliability package (Program 43.0)."""
from __future__ import annotations

from backend.core.planning.checkpoint_recovery import CheckpointRecovery
from backend.core.planning.failure_diagnosis import FailureDiagnosisEngine, FailureType, RecoveryAction
from backend.core.planning.resumable_runtime import ResumableWorkflowRuntime, PreconditionError
from backend.core.planning.decision_network import DecisionNetworkEngine
from backend.core.planning.tool_acquisition import (
    ToolRegistryExplorer,
    DependencyAnalyzer,
    SafetySandboxVerifier,
    PluginIsolationRuntime,
    TrustScoringEngine,
    CapabilityRegistryUpdater,
)
from backend.core.planning.strategy_memory import (
    StrategyMemory,
    PolicyConsolidationEngine,
    StrategyRetriever,
    MacroActionLibrary,
    ExperienceDistillationEngine,
)
from backend.core.planning.policy_distillation import PolicyDistillationEngine
from backend.core.planning.self_play import BackgroundSelfPlayEngine
from backend.core.planning.world_model import WorldModelEngine
from backend.core.planning.meta_cognition import (
    SelfAwarenessState,
    ConfidenceManager,
    ComputeAllocator,
    IntrospectionEngine,
    MetaReasoner,
)

__all__ = [
    "CheckpointRecovery",
    "FailureDiagnosisEngine",
    "FailureType",
    "RecoveryAction",
    "ResumableWorkflowRuntime",
    "PreconditionError",
    "DecisionNetworkEngine",
    "ToolRegistryExplorer",
    "DependencyAnalyzer",
    "SafetySandboxVerifier",
    "PluginIsolationRuntime",
    "TrustScoringEngine",
    "CapabilityRegistryUpdater",
    "StrategyMemory",
    "PolicyConsolidationEngine",
    "StrategyRetriever",
    "MacroActionLibrary",
    "ExperienceDistillationEngine",
    "PolicyDistillationEngine",
    "BackgroundSelfPlayEngine",
    "WorldModelEngine",
    "SelfAwarenessState",
    "ConfidenceManager",
    "ComputeAllocator",
    "IntrospectionEngine",
    "MetaReasoner",
]
