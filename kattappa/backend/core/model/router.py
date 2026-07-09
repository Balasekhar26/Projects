"""Dynamic Model Router (Program 30.0).

Resolves queries across local (low latency, offline capability) and cloud (large
scale reasoning, higher cost) models based on cost, latency, and task complexity bounds.
"""
from __future__ import annotations

from typing import Dict, Optional


class KattappaModelRouter:
    """Routes requests dynamically based on budget constraints and runtime conditions."""

    def __init__(
        self,
        local_latency_limit_ms: float = 150.0,
        cloud_cost_threshold_usd: float = 0.05,
    ) -> None:
        self.local_latency_limit_ms = local_latency_limit_ms
        self.cloud_cost_threshold_usd = cloud_cost_threshold_usd

    def route_request(
        self,
        prompt: str,
        max_cost_usd: float = 1.0,
        max_latency_ms: float = 2000.0,
        force_offline: bool = False,
    ) -> str:
        """Determines the optimal model target for the given prompt.

        Returns:
            "local" or "cloud"
        """
        # 1. Force offline overrides
        if force_offline:
            return "local"

        # 2. Strict cost restriction check
        # If the user sets a very tight cost threshold below the cloud cost trigger limit
        if max_cost_usd < self.cloud_cost_threshold_usd:
            return "local"

        # 3. Strict latency constraint check
        # If the user requires ultra-low latency execution below the local limit threshold
        if max_latency_ms <= self.local_latency_limit_ms:
            return "local"

        # 4. Complexity routing heuristics
        # Simple prompts with short lengths or instructions are routed to the local model.
        # Prompts containing keywords signifying complex planning or code edits route to cloud.
        complex_keywords = ["plan", "synthesize", "refactor", "optimize", "analyze", "debug"]
        prompt_lower = prompt.lower()
        
        is_complex = any(kw in prompt_lower for kw in complex_keywords)
        word_count = len(prompt.split())

        if is_complex or word_count > 50:
            return "cloud"

        return "local"
