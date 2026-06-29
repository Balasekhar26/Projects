"""Context Compression and Summarization Engine (Program 9).

Compresses large text values for lower-priority context items.
"""
from __future__ import annotations

import logging
from backend.core.context.models import ContextItem, ContextPriority

logger = logging.getLogger(__name__)


class CompressionEngine:
    """Summarizes or prunes text values to reduce prompt token footprint."""

    @staticmethod
    def compress_item(item: ContextItem, max_words: int = 15) -> ContextItem:
        """Compresses long string values to fit within token boundaries."""
        if not isinstance(item.value, str):
            return item

        words = item.value.split()
        if len(words) > max_words:
            # Extractive compression: take first max_words and add ellipsis
            summary = " ".join(words[:max_words]) + "..."
            logger.info("Compressed context item %s to %d words", item.item_id, max_words)
            
            item.value = summary
            # Re-estimate token counts (approx 4 chars per token)
            item.token_estimate = len(summary) // 4

        return item
