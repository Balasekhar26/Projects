"""Context Token Budget Manager (Program 9).

Allocates and enforces strict model-aware token limits across context sources.
"""
from __future__ import annotations

import logging
from typing import Dict, List
from backend.core.context.models import ContextItem, ContextSource

logger = logging.getLogger(__name__)


class ContextBudgetManager:
    """Enforces source-specific token allocations to prevent prompt starvation."""

    def __init__(self) -> None:
        # Default token budget allocations per source
        self.budgets: Dict[ContextSource, int] = {
            ContextSource.WORKING: 1000,
            ContextSource.EPISODIC: 1500,
            ContextSource.SEMANTIC: 2000,
            ContextSource.POLICY: 500,
        }

    def set_budget(self, source: ContextSource, limit: int) -> None:
        self.budgets[source] = limit

    def enforce_budgets(self, items: List[ContextItem]) -> List[ContextItem]:
        """Prunes items lists so they fit strictly within source-specific token limits."""
        allocated_tokens: Dict[ContextSource, int] = {src: 0 for src in ContextSource}
        accepted_items = []

        for item in items:
            src = item.source
            limit = self.budgets.get(src, 1000)
            estimate = item.token_estimate
            
            # If within budget, allocate tokens and accept it!
            if allocated_tokens[src] + estimate <= limit:
                allocated_tokens[src] += estimate
                accepted_items.append(item)
            else:
                logger.warning(
                    "Pruned item %s: exceeded budget allocation for %s (%d/%d)",
                    item.item_id, src.value, allocated_tokens[src], limit
                )

        return accepted_items
