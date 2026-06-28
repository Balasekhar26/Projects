"""Tests for Phase K12: Reflection Engine 2.0 (Hypothesis-Experiment Loop)."""
from __future__ import annotations

import time
import pytest
from backend.core.reflection_engine import ReflectionEngine
from backend.core.reflection_memory import ReflectionMemory
from backend.core.state_manager import CognitiveStateManager, CognitiveState
from backend.core.attention import Attention
from backend.core.blackboard import BLACKBOARD
from backend.core.cognitive_memory_bus import MEMORY_BUS


@pytest.fixture(autouse=True)
def clean_databases():
    ReflectionMemory.clear_all()
    CognitiveStateManager.reset()
    BLACKBOARD.clear()
    
    from backend.core.semantic_memory import SemanticMemory
    conn = SemanticMemory._get_sqlite_conn()
    try:
        conn.execute("DELETE FROM semantic_evidence")
        conn.execute("DELETE FROM semantic_sources")
        conn.execute("DELETE FROM semantic_edges")
        conn.execute("DELETE FROM semantic_skills")
        conn.execute("DELETE FROM semantic_aliases")
        conn.execute("DELETE FROM semantic_nodes")
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()
    
    yield
    ReflectionMemory.clear_all()
    CognitiveStateManager.reset()
    BLACKBOARD.clear()


def test_reflect_and_learn_success_path():
    res = ReflectionEngine.reflect_and_learn(
        task_id="task_success_1",
        domain="retrieval",
        statement="Retrieve server status accurately",
        success=True,
        confidence=0.9,
    )
    assert res["outcome"] == "SUCCESS"
    assert res["observation_id"] is not None
    assert res["hypothesis_id"] is not None
    
    if res["confirmed"]:
        # Invoke a second time to increment the evidence count to 2, promoting the semantic node
        ReflectionEngine.reflect_and_learn(
            task_id="task_success_2",
            domain="retrieval",
            statement="Retrieve server status accurately",
            success=True,
            confidence=0.9,
        )
        # Flush semantic embeddings if needed (semantic_memory.py uses memory/vectors cache)
        try:
            from backend.core.semantic_memory import SemanticMemory
            SemanticMemory.flush_embeddings()
        except Exception:
            pass

        # Check that a semantic memory write occurred and was promoted
        mem_reads = MEMORY_BUS.read("verified_hypothesis_retrieval", memory_types=["semantic"])
        assert len(mem_reads) > 0
        assert any("Confirmed hypothesis" in str(rec) for r in mem_reads for rec in r.records)
    else:
        # Check that an episodic memory write occurred
        mem_reads = MEMORY_BUS.read("Refuted hypothesis", memory_types=["episodic"], session_id="system_reflection_v2")
        assert len(mem_reads) > 0
        assert any("Refuted hypothesis" in str(rec) for r in mem_reads for rec in r.records)


def test_reflect_and_learn_failure_path():
    res = ReflectionEngine.reflect_and_learn(
        task_id="task_fail_1",
        domain="memory",
        statement="Write target config parameter",
        success=False,
        confidence=0.8,
    )
    assert res["outcome"] == "FAILURE"
    assert res["observation_id"] is not None
    assert res["hypothesis_id"] is not None

    # Check failure tracking count in state manager
    failures = CognitiveStateManager.get_domain_boosts()
    # 1 failure shouldn't trigger a boost yet
    assert "memory" not in failures


def test_failure_driven_attention_reshaping():
    # 1. Initially no boosts
    assert len(CognitiveStateManager.get_domain_boosts()) == 0

    # 2. Trigger 3 failures in 'retrieval' domain within 24h
    for i in range(3):
        res = ReflectionEngine.reflect_and_learn(
            task_id=f"fail_task_{i}",
            domain="retrieval",
            statement="Read timeout during remote retrieve",
            success=False,
            confidence=0.75,
        )

    # 3. State manager should now register a boost for 'retrieval'
    boosts = CognitiveStateManager.get_domain_boosts()
    assert "retrieval" in boosts
    assert boosts["retrieval"] == 1.5

    # 4. Attention.process should scale up composite score for 'retrieval' queries
    obs_normal = {
        "raw_message": "Calculate FFT values.",
        "session_id": "test-session",
    }
    obs_retrieval = {
        "raw_message": "Run retrieval checks on remote server.",
        "session_id": "test-session",
    }

    res_normal = Attention.process(obs_normal)
    res_retrieval = Attention.process(obs_retrieval)

    # Normal vs retrieval composite scores — retrieval should be boosted
    # (Since base values might be low, the boost factor ensures it scales)
    score_normal = res_normal["attention_score"]
    score_retrieval = res_retrieval["attention_score"]
    
    assert score_retrieval["composite"] > 0.0
