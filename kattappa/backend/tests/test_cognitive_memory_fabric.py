from __future__ import annotations

import time
import pytest

from backend.core.human_memory import HumanMemory
from backend.core.memory_broker import MemoryBroker
from backend.core.semantic_memory import SemanticMemory
from backend.core.episodic_memory import EpisodicMemory
from backend.core.goal_memory import GoalMemory
from backend.core.relationship_memory import RelationshipMemory


@pytest.fixture(autouse=True)
def clean_all_memories():
    HumanMemory.reset()
    try:
        SemanticMemory.reset()
    except Exception:
        pass
    try:
        EpisodicMemory.reset()
    except Exception:
        pass
    try:
        GoalMemory.reset()
    except Exception:
        pass
    yield
    HumanMemory.reset()
    try:
        SemanticMemory.reset()
    except Exception:
        pass
    try:
        EpisodicMemory.reset()
    except Exception:
        pass
    try:
        GoalMemory.reset()
    except Exception:
        pass


def test_cognitive_memory_fabric_retrieval_and_ranking():
    # 1. Populate Semantic Memory
    SemanticMemory.upsert_node(
        concept="Rust programming",
        description="Rust is a systems programming language focused on safety, speed, and concurrency.",
        source_episode_id="ep_sem_1",
        confidence=0.9
    )

    # 2. Populate Episodic Memory
    EpisodicMemory.create_episode(
        session_id="primary",
        content="User checked compiling the kattappa code using rustc today",
        importance=0.8,
        category="PLANNING"
    )

    # 3. Populate Goal Memory
    GoalMemory.create_goal(
        title="Compile Kattappa with Rust",
        description="Port execution speed bottlenecks to native Rust extensions.",
        priority="HIGH",
        confidence_score=95.0
    )

    # 4. Populate Belief System
    HumanMemory.upsert_belief("preferred_language", "Rust", 0.98)

    # 5. Populate Relationship notes
    RelationshipMemory.get_or_create_entity(entity_id="bala", name="Bala", entity_type="user")
    RelationshipMemory.set_preference("bala", "general", "language", "Rust")

    # Flush background embedding queues
    try:
        SemanticMemory._embed_queue.join()
    except Exception:
        pass
    try:
        EpisodicMemory.flush_embeddings()
    except Exception:
        pass

    # Execute Unified Retrieve
    result = MemoryBroker.retrieve(query="Rust safety speed", limit=5)
    
    assert "top_candidates" in result
    assert "unified_context_string" in result
    assert "relationship_notes" in result
    
    candidates = result["top_candidates"]
    assert len(candidates) >= 1
    
    # Check that candidate types are mapped properly
    types = {c["type"] for c in candidates}
    assert any(t in types for t in ["semantic", "episodic", "goal", "belief"])
    
    # Assert unified context string contains structured content
    ctx_str = result["unified_context_string"]
    assert "### Unified Memory Context" in ctx_str
    assert "Rust" in ctx_str
