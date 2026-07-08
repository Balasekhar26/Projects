"""Context Attention Selection Manager (Program 9).

Determines inclusion priority categories (Must, Should, Optional, Ignore) before prompt construction.
"""
from __future__ import annotations

from typing import List
from backend.core.context.models import ContextItem, ContextPriority


class AttentionManager:
    """Filters and updates item inclusion priorities based on relevance queries."""

    @staticmethod
    def adjust_priorities(items: List[ContextItem], query: str) -> List[ContextItem]:
        """Toggles priority categories based on exact keyword matches in item values."""
        adjusted = []
        q = query.lower()

        for item in items:
            val_str = str(item.value).lower()
            
            # If the item value directly contains the exact query word, upgrade it!
            if q in val_str:
                if item.priority == ContextPriority.OPTIONAL:
                    item.priority = ContextPriority.SHOULD
                elif item.priority == ContextPriority.SHOULD:
                    item.priority = ContextPriority.MUST
            else:
                # Downgrade if it doesn't match
                if item.priority == ContextPriority.MUST:
                    item.priority = ContextPriority.SHOULD
                elif item.priority == ContextPriority.SHOULD:
                    item.priority = ContextPriority.OPTIONAL

            adjusted.append(item)

        return adjusted
