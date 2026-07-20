"""Lazy public surface for the Kattappa persistent-memory package.

Importing ``backend.main`` must not initialize Chroma, ONNX Runtime, or every
memory store. PEP 562 lazy exports preserve the historical import API while
loading only the store or legacy helper explicitly requested by a caller.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "MemoryRecord": (".schemas", "MemoryRecord"),
    "MemoryType": (".schemas", "MemoryType"),
    "IMemoryStore": (".memory_manager", "IMemoryStore"),
    "MemoryManager": (".memory_manager", "MemoryManager"),
    "WorkingMemoryStore": (".working_memory_store", "WorkingMemoryStore"),
    "EpisodicMemoryStore": (".episodic_memory_store", "EpisodicMemoryStore"),
    "ConsolidationEngine": (".consolidation_engine", "ConsolidationEngine"),
    "ConsolidationReport": (".consolidation_engine", "ConsolidationReport"),
    "SemanticMemoryStore": (".semantic_memory_store", "SemanticMemoryStore"),
    "ProceduralMemoryStore": (".procedural_memory_store", "ProceduralMemoryStore"),
    "ReflectionMemoryStore": (".reflection_memory_store", "ReflectionMemoryStore"),
    "PolicyMemoryStore": (".policy_memory_store", "PolicyMemoryStore"),
    "memory": (".legacy", "memory"),
    "remember": (".legacy", "remember"),
    "recall": (".legacy", "recall"),
    "build_memory_context": (".legacy", "build_memory_context"),
    "get_git_status": (".legacy", "get_git_status"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
