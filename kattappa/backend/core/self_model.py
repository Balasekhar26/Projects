"""Self Model — Phase K17.5.

Tracks Kattappa's own capabilities, resource load, active tool registry,
and historical failure rates to return self-confidence scores and boundary limits.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from backend.core.logger import log_event

logger = logging.getLogger(__name__)


class SelfModel:
    """Represents Kattappa's internal state, capabilities, and self-confidence boundaries."""

    @classmethod
    def get_capabilities(cls) -> Dict[str, Any]:
        """Returns the registered capabilities and tools currently installed."""
        from backend.core.orchestrator.registry import ORCHESTRATOR_REGISTRY
        agents = [a.name for a in ORCHESTRATOR_REGISTRY.all()]
        
        return {
            "installed_agents": agents,
            "available_tools": ["calculator", "file_writer", "shell_executor"],
            "max_concurrent_tasks": 4,
            "wisdom_engine_enabled": True
        }

    @classmethod
    def evaluate_capability(
        cls,
        task_query: str,
        current_load: float = 0.2
    ) -> Tuple[bool, float, str]:
        """Evaluates whether the system has the capability to execute a task confidently.

        Returns:
            (can_execute, self_confidence_score, reason)
        """
        query_lower = task_query.lower()
        capabilities = cls.get_capabilities()

        # Check resource load boundaries
        # If load is excessively high, we flag danger boundary
        if current_load >= 0.90:
            log_event("self_model_boundary_halt", f"System load limit exceeded (load={current_load:.2f})")
            return False, 0.10, "System resource limits reached. Cannot execute safely."

        # Check capability matches
        # Suppose a user asks for unsupported tasks like "train image model" or "compile C++ kernel"
        unsupported = ["train image model", "c++ compiler", "hack database", "mine crypto"]
        for term in unsupported:
            if term in query_lower:
                log_event("self_model_boundary_unsupported", f"Unsupported task requested: {term}")
                return False, 0.0, f"Unsupported capability: {term}"

        # Base confidence calculation based on load and keyword matches
        confidence = 0.95 - (current_load * 0.2)
        
        # If the task requires external tools we check if they exist
        if "calculate" in query_lower and "calculator" not in capabilities["available_tools"]:
            return False, 0.0, "Required tool 'calculator' not available"

        log_event("self_model_evaluation", f"Self Model capability check passed (confidence={confidence:.2f})")
        return True, round(confidence, 2), "Task fits system capabilities and load limits"
