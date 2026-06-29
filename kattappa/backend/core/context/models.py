"""Context Engine Data Models (Program 9).

Defines the ContextItem schema and provider-agnostic ContextBundle payload.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class ContextSource(str, Enum):
    WORKING = "WorkingMemory"
    EPISODIC = "EpisodicMemory"
    SEMANTIC = "SemanticMemory"
    POLICY = "Policy"


class ContextPriority(str, Enum):
    MUST = "Must"
    SHOULD = "Should"
    OPTIONAL = "Optional"
    IGNORE = "Ignore"


@dataclass
class ContextItem:
    """A prioritized slice of context state."""
    item_id: str
    source: ContextSource
    value: Any
    priority: ContextPriority = ContextPriority.SHOULD
    token_estimate: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextBundle:
    """Aggregated, provider-agnostic package ready for prompt generation."""
    session_id: str
    items: List[ContextItem] = field(default_factory=list)
    total_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_provider_prompt(self) -> Dict[str, Any]:
        """Utility compiling items list to basic text payloads."""
        system_rules = []
        user_instructions = []
        context_facts = []

        # Sort items: MUST first, then SHOULD, then OPTIONAL
        sorted_items = sorted(
            [item for item in self.items if item.priority != ContextPriority.IGNORE],
            key=lambda x: (
                0 if x.priority == ContextPriority.MUST
                else 1 if x.priority == ContextPriority.SHOULD
                else 2
            )
        )

        for item in sorted_items:
            val_str = str(item.value)
            if item.source == ContextSource.POLICY:
                system_rules.append(val_str)
            elif item.source == ContextSource.WORKING:
                user_instructions.append(f"[WorkingState] {val_str}")
            else:
                context_facts.append(f"[MemoryFact] {val_str}")

        return {
            "system": "\n".join(system_rules),
            "context": "\n".join(context_facts),
            "user": "\n".join(user_instructions),
        }
