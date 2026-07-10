"""
backend/core/memory/__init__.py

Public surface of the Kattappa Persistent Memory Engine (v0.2).

Legacy compatibility:
  The original memory.py (now hosted in legacy.py) exposed a module-level
  singleton and several helper functions used across the codebase.  All
  existing imports of the form:

      from backend.core.memory import memory
      from backend.core.memory import memory, remember
      from backend.core.memory import build_memory_context, memory, recall, remember
      from backend.core.memory import get_git_status

  continue to resolve correctly through these re-exports.
"""

# Phase 1A — contracts and registry
from .schemas import MemoryRecord, MemoryType
from .memory_manager import IMemoryStore, MemoryManager

# Phase 1B — Working Memory Store
from .working_memory_store import WorkingMemoryStore

# Phase 1C — Episodic Memory Store
from .episodic_memory_store import EpisodicMemoryStore

# Phase 1D — Consolidation Engine
from .consolidation_engine import ConsolidationEngine, ConsolidationReport

# Phase 2A — Semantic Memory Store
from .semantic_memory_store import SemanticMemoryStore

# Phase 2C — Procedural Memory Store
from .procedural_memory_store import ProceduralMemoryStore

# Phase 3A — Reflection Memory Store
from .reflection_memory_store import ReflectionMemoryStore

# Phase 3B — Policy Memory Store
from .policy_memory_store import PolicyMemoryStore

# Legacy compatibility — MemorySystem singleton and helpers
from .legacy import memory, remember, recall, build_memory_context, get_git_status

__all__ = [
    # v0.2 contracts
    "MemoryRecord",
    "MemoryType",
    "IMemoryStore",
    "MemoryManager",
    # v0.2 stores
    "WorkingMemoryStore",
    "EpisodicMemoryStore",
    "ConsolidationEngine",
    "ConsolidationReport",
    "SemanticMemoryStore",
    "ProceduralMemoryStore",
    "ReflectionMemoryStore",
    "PolicyMemoryStore",
    # Legacy (v0.1-compatible)
    "memory",
    "remember",
    "recall",
    "build_memory_context",
    "get_git_status",
]
