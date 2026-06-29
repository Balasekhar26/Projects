"""Master Context Engine Coordinator (Program 9).

Orchestrates retrievals, ranking, attention prioritizing, budgeting, compressing,
and caching to build structured prompts.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.context.models import ContextBundle, ContextItem
from backend.core.context.memories import WorkingMemoryLayer, EpisodicMemoryLayer, SemanticMemoryLayer
from backend.core.context.retriever import MemoryRetriever
from backend.core.context.ranking import RankingEngine
from backend.core.context.attention import AttentionManager
from backend.core.context.compression import CompressionEngine
from backend.core.context.budget import ContextBudgetManager
from backend.core.context.assembler import ContextAssembler
from backend.core.context.cache import ContextCache

logger = logging.getLogger(__name__)


class ContextEngine:
    """Master controller managing the Kattappa context management platform pipeline."""

    _instance: Optional[ContextEngine] = None

    def __init__(self) -> None:
        self.working = WorkingMemoryLayer()
        self.episodic = EpisodicMemoryLayer()
        self.semantic = SemanticMemoryLayer()
        
        self.retriever = MemoryRetriever(self.working, self.episodic, self.semantic)
        self.budget_mgr = ContextBudgetManager()
        self.cache = ContextCache()

    @classmethod
    def get_instance(cls) -> ContextEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def assemble_context(
        self,
        session_id: str,
        query: str,
        bypass_cache: bool = False,
    ) -> ContextBundle:
        """Runs the context compile pipeline, enforcing token constraints and cache hits."""
        # 1. Cache hit check
        if not bypass_cache:
            cached = self.cache.get(session_id)
            if cached:
                logger.info("Context Cache hit for session: %s", session_id)
                return cached

        logger.info("Context Cache miss. Compiling context bundle for: %s", session_id)

        # 2. Retrieve candidates
        candidates = self.retriever.retrieve(query)

        # 3. Adjust priorities using pre-inference attention manager
        candidates = AttentionManager.adjust_priorities(candidates, query)

        # 4. Compress long text item values
        compressed_candidates = []
        for item in candidates:
            compressed_candidates.append(CompressionEngine.compress_item(item))

        # 5. Rank items deterministically
        ranked = RankingEngine.score_and_rank(compressed_candidates)

        # 6. Enforce token budgets
        budgeted = self.budget_mgr.enforce_budgets(ranked)

        # 7. Assemble final bundle
        bundle = ContextAssembler.assemble(session_id, budgeted)

        # Cache compiled result
        self.cache.put(session_id, bundle)

        return bundle
