"""
Dynamic Model Router — Step 30
==============================

Estimates query difficulty and routes requests dynamically to appropriate model
scales based on system resources and complexity.
"""

from __future__ import annotations

from typing import List

from kattappa_runtime.resource_governor.governor import ResourceGovernor


class DifficultyEstimator:
    """
    Categorises user queries into difficulty levels based on syntactic and keyword rules.
    """
    def __init__(self):
        self.coding_keywords = {
            "def ", "class ", "import ", "python", "javascript", "code", "bug", "refactor",
            "test", "compile", "script", "function", "array", "database", "sql"
        }
        self.complex_keywords = {
            "analyze", "compare", "research", "plan", "audit", "solve", "explain how",
            "optimize", "design", "synthesize", "architect", "why did", "debug", "proof"
        }

    def estimate_difficulty(self, query: str) -> str:
        """
        Estimates difficulty: 'simple', 'medium', or 'complex'.
        """
        query_lower = query.lower()
        
        # Check complex keywords first
        if any(kw in query_lower for kw in self.complex_keywords):
            return "complex"
            
        # Check coding keywords
        if any(kw in query_lower for kw in self.coding_keywords):
            return "medium"
            
        # Default simple
        return "simple"


class DynamicModelRouter:
    """
    Selects model sizes (Tiny/137M, Medium/1B, Large/7B) based on difficulty and available system headroom.
    """
    def __init__(self, governor: ResourceGovernor):
        self.governor = governor
        self.estimator = DifficultyEstimator()

    def route(self, query: str) -> str:
        """
        Routes query to 'tiny', 'medium', or 'large'.
        """
        difficulty = self.estimator.estimate_difficulty(query)
        metrics = self.governor.monitor.get_metrics()
        
        # Safe thresholds
        ram_percent = metrics.ram_percent
        temp = metrics.temperature_c

        if difficulty == "simple":
            return "tiny"

        elif difficulty == "medium":
            # Select Medium model only if system RAM is below target 50% limit
            if ram_percent < (self.governor.config.global_ram_limit * 100):
                return "medium"
            return "tiny"

        else: # complex
            # Select Large model if RAM is well within limit and temperature is cool
            if ram_percent < (self.governor.config.global_ram_limit * 100 - 10.0) and temp < 75.0:
                return "large"
            # Fallback to Medium if RAM allows
            if ram_percent < (self.governor.config.global_ram_limit * 100):
                return "medium"
            return "tiny"
