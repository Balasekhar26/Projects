"""Context Assembler Engine (Program 9).

Compiles filtered items into provider-agnostic ContextBundle packages, deduplicating facts.
"""
from __future__ import annotations

import logging
import time
from typing import List, Set, Optional, Dict, Any
from backend.core.context.models import ContextBundle, ContextItem, ContextPriority, ContextSource

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

    @staticmethod
    def build(
        goal: Optional[Dict[str, Any]],
        memories: List[Dict[str, Any]],
        tools: Dict[str, Any],
        environment: Dict[str, Any],
        conversation: List[Dict[str, Any]],
        token_budget: int = 4096,
        ttl_seconds: Optional[float] = None
    ) -> ContextBundle:
        """Assembles all cognitive contexts into one ContextBundle object."""
        items: List[ContextItem] = []
        now = time.time()

        # Helper to compute token estimate (length in words * 1.3)
        def estimate_tokens(text: str) -> int:
            return int(len(text.split()) * 1.3)

        # 1. Goal Context (MUST priority)
        if goal:
            val_str = f"Active Goal: {goal.get('title') or goal.get('name')} - {goal.get('description', '')}"
            items.append(
                ContextItem(
                    item_id=f"goal-{goal.get('goal_id') or 'current'}",
                    source=ContextSource.WORKING,
                    value=val_str,
                    priority=ContextPriority.MUST,
                    token_estimate=estimate_tokens(val_str),
                    timestamp=float(goal.get("timestamp", now)),
                    metadata={
                        "provenance": "goal_database",
                        "confidence": float(goal.get("confidence", 1.0))
                    }
                )
            )

        # 2. Memories Context (SHOULD priority)
        for idx, m in enumerate(memories):
            val_str = m.get("content") or m.get("description") or ""
            if not val_str:
                continue
            items.append(
                ContextItem(
                    item_id=f"mem-{m.get('id') or idx}",
                    source=ContextSource.SEMANTIC if m.get("category") != "episodic" else ContextSource.EPISODIC,
                    value=val_str,
                    priority=ContextPriority.SHOULD,
                    token_estimate=estimate_tokens(val_str),
                    timestamp=float(m.get("timestamp", now)),
                    metadata={
                        "provenance": m.get("source", "semantic_memory"),
                        "confidence": float(m.get("confidence", 0.90))
                    }
                )
            )

        # 3. Tool States (SHOULD priority)
        if tools:
            val_str = f"Tools Reliability: {tools}"
            items.append(
                ContextItem(
                    item_id="tools-reliability",
                    source=ContextSource.SEMANTIC,
                    value=val_str,
                    priority=ContextPriority.SHOULD,
                    token_estimate=estimate_tokens(val_str),
                    timestamp=now,
                    metadata={
                        "provenance": "tool_reliability_tracker",
                        "confidence": 1.0
                    }
                )
            )

        # 4. Environment Context (SHOULD priority)
        if environment:
            val_str = f"Telemetry: {environment}"
            items.append(
                ContextItem(
                    item_id="environment-telemetry",
                    source=ContextSource.WORKING,
                    value=val_str,
                    priority=ContextPriority.SHOULD,
                    token_estimate=estimate_tokens(val_str),
                    timestamp=now,
                    metadata={
                        "provenance": "state_manager",
                        "confidence": 1.0
                    }
                )
            )

        # 5. Conversation History (MUST priority for recent, SHOULD for older)
        for idx, msg in enumerate(conversation):
            val_str = f"[{msg.get('role', 'user')}]: {msg.get('content', '')}"
            priority = ContextPriority.MUST if (len(conversation) - idx) <= 3 else ContextPriority.SHOULD
            items.append(
                ContextItem(
                    item_id=f"msg-{idx}",
                    source=ContextSource.WORKING,
                    value=val_str,
                    priority=priority,
                    token_estimate=estimate_tokens(val_str),
                    timestamp=float(msg.get("timestamp", now)),
                    metadata={
                        "provenance": "conversation_history",
                        "confidence": 1.0
                    }
                )
            )

        # Expiration (TTL) check
        valid_items = []
        for item in items:
            if ttl_seconds is not None and (now - item.timestamp) > ttl_seconds:
                continue
            valid_items.append(item)

        # Deduplicate exact duplicate values
        seen_values = set()
        unique_items = []
        for item in valid_items:
            val_str = str(item.value).strip()
            if val_str not in seen_values:
                seen_values.add(val_str)
                unique_items.append(item)

        # Sort priority: MUST (0) -> SHOULD (1) -> OPTIONAL (2)
        sorted_items = sorted(
            unique_items,
            key=lambda x: (
                0 if x.priority == ContextPriority.MUST
                else 1 if x.priority == ContextPriority.SHOULD
                else 2
            )
        )

        # Token budgeting loop (memory compression/truncation)
        allocated_items = []
        current_tokens = 0
        for item in sorted_items:
            item_tokens = item.token_estimate
            if current_tokens + item_tokens <= token_budget:
                allocated_items.append(item)
                current_tokens += item_tokens
            else:
                # Memory Compression / Truncation
                remaining_budget = token_budget - current_tokens
                if remaining_budget > 10 and item.priority in (ContextPriority.MUST, ContextPriority.SHOULD):
                    words = str(item.value).split()
                    max_words = int(remaining_budget / 1.3)
                    if max_words > 3:
                        compressed_value = " ".join(words[:max_words]) + "..."
                        item.value = compressed_value
                        item.token_estimate = estimate_tokens(compressed_value)
                        allocated_items.append(item)
                        current_tokens += item.token_estimate
                break

        return ContextBundle(
            session_id="assembled-bundle",
            items=allocated_items,
            total_tokens=current_tokens,
            metadata={
                "timestamp": now,
                "token_budget": token_budget,
                "ttl_seconds": ttl_seconds
            }
        )

