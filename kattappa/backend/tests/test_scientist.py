"""Tests for Phase K14: Scientist Agent."""
from __future__ import annotations

import pytest
from backend.core.scientist import Scientist
from backend.core.orchestrator.registry import ORCHESTRATOR_REGISTRY
from backend.core.orchestrator.base import Task
from backend.core.orchestrator.context import SharedContext
from backend.core.cognitive_memory_bus import MEMORY_BUS
from backend.core.graph import _get_kg


@pytest.fixture(autouse=True)
def clean_kg():
    kg = _get_kg()
    if kg is not None:
        with kg._store._lock:
            conn = kg._store._get_conn()
            conn.execute("DELETE FROM kg_nodes")
            conn.commit()
            conn.close()
    yield


def test_scientist_propose_hypotheses():
    context = {"statement": "Optimizing memory retrievals improves latency", "confidence": 0.9}
    candidates = Scientist.propose_hypotheses("memory", context)
    assert len(candidates) == 1
    assert candidates[0]["domain"] == "memory"
    assert candidates[0]["statement"] == "Optimizing memory retrievals improves latency"
    assert candidates[0]["confidence"] == 0.9


def test_scientist_disprover_absolute_claim_penalty():
    # Absolute statement should be penalized
    hyp_absolute = {
        "statement": "Always execute planning steps in sequence",
        "domain": "planning",
        "confidence": 0.8
    }
    p_abs = Scientist.falsify_hypothesis(hyp_absolute)
    
    # Non-absolute statement
    hyp_normal = {
        "statement": "Optimizing execution paths resolves planning lag",
        "domain": "planning",
        "confidence": 0.8
    }
    p_norm = Scientist.falsify_hypothesis(hyp_normal)
    
    assert p_abs < p_norm


def test_scientist_disprover_semantic_contradiction_falsifies():
    # Write a failure statement to semantic memory twice to promote it
    for i in range(2):
        MEMORY_BUS.write(
            memory_type="semantic",
            data={
                "concept": "planning failure patterns",
                "description": "Always check for planning fail status",
                "source_episode_id": f"test_scientist_{i}",
                "provenance": "test_runner",
            },
            confidence=0.9,
            verified=True
        )
    
    # Flush semantic embeddings if needed
    try:
        from backend.core.semantic_memory import SemanticMemory
        SemanticMemory.flush_embeddings()
    except Exception:
        pass

    hyp = {
        "statement": "Always check for planning fail status",
        "domain": "planning",
        "confidence": 0.9
    }
    # Should find the semantic contradiction and return 0.0
    p = Scientist.falsify_hypothesis(hyp)
    assert p == 0.0


def test_scientist_evaluate_and_commit_thresholds():
    # Hypothesis that survives disproof with P >= 0.95
    hyp_strong = {
        "statement": "Optimizing semantic reads resolves retrieval delay",
        "domain": "memory",
        "confidence": 0.95
    }
    res_strong = Scientist.evaluate_and_commit(hyp_strong)
    assert res_strong["status"] == "COMMITTED"
    assert res_strong["p_survival"] >= 0.95
    
    # Retrieve from KG and verify state is BELIEVED
    kg = _get_kg()
    node_strong = kg.resolve_entity(hyp_strong["statement"])
    assert node_strong is not None
    assert node_strong.belief_state == "BELIEVED"
    
    # Hypothesis that fails threshold
    hyp_weak = {
        "statement": "Simple sequential checks always solve memory gaps",
        "domain": "memory",
        "confidence": 0.4
    }
    res_weak = Scientist.evaluate_and_commit(hyp_weak)
    assert res_weak["status"] == "REFUTED"
    assert res_weak["p_survival"] < 0.95
    
    # Retrieve from KG and verify state is REFUTED
    node_weak = kg.resolve_entity(hyp_weak["statement"])
    assert node_weak is not None
    assert node_weak.belief_state == "REFUTED"


def test_scientist_agent_orchestration():
    agent = ORCHESTRATOR_REGISTRY.get("scientist")
    assert agent is not None
    
    task = Task(
        task_id="task_scientist_test",
        agent_name="scientist",
        action="falsify",
        params={
            "domain": "memory",
            "statement": "Optimizing temporal graph indices resolves retrieval delay",
            "confidence": 0.95
        }
    )
    
    context = SharedContext()
    result = agent.execute(task, context)
    assert result.success
    assert result.output["status"] == "COMMITTED"
    assert context.get("scientist_outcome") is not None
