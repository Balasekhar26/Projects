"""Unit and integration tests for Program 9: Context Management Platform.
"""
from __future__ import annotations

import time
import pytest
from typing import List

from backend.core.context.models import ContextBundle, ContextItem, ContextPriority, ContextSource
from backend.core.context.memories import WorkingMemoryLayer, EpisodicMemoryLayer, SemanticMemoryLayer
from backend.core.context.retriever import MemoryRetriever
from backend.core.context.ranking import RankingEngine
from backend.core.context.attention import AttentionManager
from backend.core.context.compression import CompressionEngine
from backend.core.context.budget import ContextBudgetManager
from backend.core.context.assembler import ContextAssembler
from backend.core.context.cache import ContextCache
from backend.core.context.context_engine import ContextEngine


def test_isolated_memory_layers():
    """Verifies data separation across working, episodic, and semantic layers."""
    wm = WorkingMemoryLayer(active_task="DeploySystem", execution_variables={"port": 8080})
    ep = EpisodicMemoryLayer()
    ep.add_run("sess_1", "Completed", 12.5)
    sm = SemanticMemoryLayer()
    sm.add_policy("Always verify authorization preflight")

    assert wm.active_task == "DeploySystem"
    assert wm.execution_variables["port"] == 8080
    assert len(ep.recent_runs) == 1
    assert sm.static_policies[0].startswith("Always verify")


def test_memory_retriever_query():
    """Verifies that MemoryRetriever retrieves context items matching query keyword filters."""
    wm = WorkingMemoryLayer(active_task="WriteCode")
    ep = EpisodicMemoryLayer()
    sm = SemanticMemoryLayer()
    sm.add_policy("Rule: Code quality should be high")

    retriever = MemoryRetriever(wm, ep, sm)
    
    # Matching query
    results = retriever.retrieve("code")
    assert len(results) == 2  # Matches WriteCode and Rule: Code quality
    assert results[0].source == ContextSource.WORKING
    assert results[1].source == ContextSource.POLICY

    # Non-matching query
    assert len(retriever.retrieve("nonexistent")) == 0


def test_ranking_engine_sorting():
    """Verifies RankingEngine sorts items prioritising MUST and POLICY sources."""
    item1 = ContextItem("1", ContextSource.SEMANTIC, "Fact1", ContextPriority.OPTIONAL, 10)
    item2 = ContextItem("2", ContextSource.POLICY, "Fact2", ContextPriority.MUST, 20)
    item3 = ContextItem("3", ContextSource.WORKING, "Fact3", ContextPriority.SHOULD, 30)

    ranked = RankingEngine.score_and_rank([item1, item2, item3])
    # item2 (MUST + POLICY) should rank first, then item3 (SHOULD + WORKING), then item1 (OPTIONAL)
    assert ranked[0].item_id == "2"
    assert ranked[1].item_id == "3"
    assert ranked[2].item_id == "1"


def test_attention_prioritization_adjustments():
    """Verifies AttentionManager adjusts priorities based on query match context."""
    item = ContextItem("1", ContextSource.WORKING, "Active deployment", ContextPriority.SHOULD, 10)
    
    # Contains query "deploy" -> upgrade to MUST
    res = AttentionManager.adjust_priorities([item], "deploy")
    assert res[0].priority == ContextPriority.MUST

    # Does not contain query "auth" -> downgrade to SHOULD
    res_down = AttentionManager.adjust_priorities([item], "auth")
    assert res_down[0].priority == ContextPriority.SHOULD


def test_compression_engine_summarization():
    """Verifies CompressionEngine summarizes values that exceed length boundaries."""
    long_text = "This is a very long memory context item that contains many words and details which must be compressed."
    item = ContextItem("1", ContextSource.WORKING, long_text, ContextPriority.OPTIONAL, 100)

    compressed = CompressionEngine.compress_item(item, max_words=5)
    # Should contain first 5 words + ellipsis
    assert compressed.value == "This is a very long..."
    assert compressed.token_estimate == len("This is a very long...") // 4


def test_context_budget_enforcement():
    """Verifies ContextBudgetManager filters items exceeding source allocations."""
    manager = ContextBudgetManager()
    manager.set_budget(ContextSource.WORKING, 50)

    item1 = ContextItem("1", ContextSource.WORKING, "v1", ContextPriority.MUST, 30)
    item2 = ContextItem("2", ContextSource.WORKING, "v2", ContextPriority.SHOULD, 30)  # Overflows budget limit of 50

    budgeted = manager.enforce_budgets([item1, item2])
    assert len(budgeted) == 1
    assert budgeted[0].item_id == "1"


def test_context_assembler_deduplication():
    """Verifies ContextAssembler deduplicates facts and compiles ContextBundle."""
    item1 = ContextItem("1", ContextSource.WORKING, "DeploySystem", ContextPriority.MUST, 10)
    item2 = ContextItem("2", ContextSource.SEMANTIC, "DeploySystem", ContextPriority.SHOULD, 20)  # Duplicated value string!

    bundle = ContextAssembler.assemble("session_123", [item1, item2])
    assert len(bundle.items) == 1
    assert bundle.items[0].item_id == "1"
    assert bundle.total_tokens == 10


def test_context_cache_lru_ttl():
    """Verifies TTL and LRU evictions on ContextCache."""
    cache = ContextCache(capacity=2, ttl_seconds=0.1)
    
    bundle1 = ContextBundle("sess_1")
    bundle2 = ContextBundle("sess_2")
    bundle3 = ContextBundle("sess_3")

    # Put and get
    cache.put("sess_1", bundle1)
    assert cache.get("sess_1") == bundle1

    # Capacity limits (sess_1 should be evicted when sess_3 is put)
    cache.put("sess_2", bundle2)
    cache.put("sess_3", bundle3)
    assert cache.get("sess_1") is None
    assert cache.get("sess_2") == bundle2
    assert cache.get("sess_3") == bundle3

    # TTL eviction
    time.sleep(0.15)
    assert cache.get("sess_2") is None
