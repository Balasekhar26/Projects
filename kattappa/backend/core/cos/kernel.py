"""Cognitive Kernel — Phase K9.5.

Acts as the central capability and routing kernel for Kattappa, coordinating
all system buses (Memory, Goals, Events, Context, Tools, Agents) to prevent
subsystem coupling.
"""

from __future__ import annotations

# Re-export classes and singleton from cognitive_kernel to maintain backward compatibility
from backend.core.cognitive_kernel import (
    CognitiveKernel,
    KERNEL,
    MemoryBus,
    GoalBus,
    EventBus,
    ContextBus,
    ToolBus,
    AgentBus,
)
