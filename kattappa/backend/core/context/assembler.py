"""Context Assembler Engine (Program 9).

Compiles filtered items into provider-agnostic ContextBundle packages, deduplicating facts.
"""
from __future__ import annotations

import logging
from typing import List, Set
from backend.core.context.models import ContextBundle, ContextItem

logger = logging.getLogger(__name__)


class ContextAssembler:
    """Consolidates and deduplicates context items list to assemble final bundle."""

    @staticmethod
    def assemble(session_id: str, items: List[ContextItem]) -> ContextBundle:
        """Deduplicates and compiles items into one ContextBundle."""
        seen_values: Set[str] = set()
        unique_items = []
        total_tokens = 0

        for item in items:
            val_str = str(item.value).strip()
            # Basic semantic deduplication: ignore exact duplicate strings
            if val_str in seen_values:
                logger.debug("Deduplicated context item: %s", item.item_id)
                continue

            seen_values.add(val_str)
            unique_items.append(item)
            total_tokens += item.token_estimate

        return ContextBundle(
            session_id=session_id,
            items=unique_items,
            total_tokens=total_tokens,
        )
