"""Context Retriever Engine (Program 9).

Unified retriever interfaces scanning working, episodic, and semantic memory layers.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import List

from backend.core.context.models import ContextItem, ContextPriority, ContextSource
from backend.core.context.memories import WorkingMemoryLayer, EpisodicMemoryLayer, SemanticMemoryLayer


class RetrieverInterface(ABC):
    """Abstract contract for pluggable context search databases."""

    @abstractmethod
    def retrieve(self, query: str) -> List[ContextItem]:
        pass


class MemoryRetriever(RetrieverInterface):
    """Scans local memory layers to fetch candidate context items matching the query."""

    def __init__(
        self,
        working: WorkingMemoryLayer,
        episodic: EpisodicMemoryLayer,
        semantic: SemanticMemoryLayer,
    ) -> None:
        self.working = working
        self.episodic = episodic
        self.semantic = semantic

    def retrieve(self, query: str) -> List[ContextItem]:
        """Searches all memory layers for matching keywords in values."""
        results: List[ContextItem] = []
        q = query.lower()

        # 1. Search working memory
        if self.working.active_task and q in self.working.active_task.lower():
            results.append(
                ContextItem(
                    item_id=f"wm_task_{uuid.uuid4().hex[:4]}",
                    source=ContextSource.WORKING,
                    value=f"Active Task: {self.working.active_task}",
                    priority=ContextPriority.MUST,
                    token_estimate=50,
                )
            )

        # Search variables
        for key, val in self.working.execution_variables.items():
            if q in key.lower() or q in str(val).lower():
                results.append(
                    ContextItem(
                        item_id=f"wm_var_{key}",
                        source=ContextSource.WORKING,
                        value=f"Exec Variable: {key} = {val}",
                        priority=ContextPriority.SHOULD,
                        token_estimate=40,
                    )
                )

        # 2. Search episodic failures/runs
        for run in self.episodic.recent_runs:
            if q in str(run.values()).lower():
                results.append(
                    ContextItem(
                        item_id=f"ep_run_{run['session_id']}",
                        source=ContextSource.EPISODIC,
                        value=f"Recent Session {run['session_id']} ended in state: {run['status']}",
                        priority=ContextPriority.OPTIONAL,
                        token_estimate=60,
                    )
                )

        # 3. Search semantic policies
        for idx, policy in enumerate(self.semantic.static_policies):
            if q in policy.lower():
                results.append(
                    ContextItem(
                        item_id=f"sm_policy_{idx}",
                        source=ContextSource.POLICY,
                        value=policy,
                        priority=ContextPriority.MUST,
                        token_estimate=len(policy) // 4,
                    )
                )

        return results
class MockVectorRetriever(RetrieverInterface):
    """Simulated pluggable vector DB search retriever."""

    def retrieve(self, query: str) -> List[ContextItem]:
        return [
            ContextItem(
                item_id="vec_node_1",
                source=ContextSource.SEMANTIC,
                value=f"Vector DB fact about '{query}'",
                priority=ContextPriority.SHOULD,
                token_estimate=30,
            )
        ]
