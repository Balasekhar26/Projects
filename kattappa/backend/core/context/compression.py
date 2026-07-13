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
            from backend.core.model_router import ask_model
            prompt = (
                f"Perform high-quality semantic compression/summarization of the following context item. "
                f"Compress it down to at most {max_words} words while preserving critical semantic facts:\n\n"
                f"{item.value}"
            )
            try:
                summary = ask_model(prompt, role="compression").strip()
                if not summary or len(summary.split()) > max_words * 2:
                    summary = " ".join(words[:max_words]) + "..."
            except Exception:
                summary = " ".join(words[:max_words]) + "..."
                
            logger.info("Compressed context item %s dynamically", item.item_id)
            item.value = summary
            item.token_estimate = len(summary) // 4

        return item
