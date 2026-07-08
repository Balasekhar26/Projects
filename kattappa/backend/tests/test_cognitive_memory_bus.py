"""Tests for Phase K8: CognitiveMemoryBus."""
from __future__ import annotations

import pytest
from backend.core.cognitive_memory_bus import (
    CognitiveMemoryBus,
    MEMORY_BUS,
    POLICIES,
    StoragePolicy,
    WriteResult,
    ReadResult,
)


# ── StoragePolicy tests ────────────────────────────────────────────────────────

def test_all_memory_types_have_policies():
    for mt in ["working", "episodic", "semantic", "procedural", "long_term", "knowledge_graph"]:
        assert mt in POLICIES, f"Missing policy for {mt!r}"


def test_storage_policy_confidence_values():
    assert POLICIES["working"].min_confidence == 0.20
    assert POLICIES["episodic"].min_confidence == 0.45
    assert POLICIES["semantic"].min_confidence == 0.75
    assert POLICIES["procedural"].min_confidence == 0.90
    assert POLICIES["knowledge_graph"].min_confidence == 0.95


def test_storage_policy_flags():
    assert POLICIES["procedural"].requires_verification is True
    assert POLICIES["long_term"].human_approval_required is True
    assert POLICIES["semantic"].triggers_kg_sync is True
    assert POLICIES["knowledge_graph"].triggers_kg_sync is True
    assert POLICIES["working"].triggers_kg_sync is False


# ── Singleton test ─────────────────────────────────────────────────────────────

def test_bus_is_singleton():
    bus1 = CognitiveMemoryBus()
    bus2 = CognitiveMemoryBus()
    assert bus1 is bus2
    assert bus1 is MEMORY_BUS


# ── Write gate enforcement ─────────────────────────────────────────────────────

def test_write_unknown_memory_type_fails():
    result = MEMORY_BUS.write("quantum_memory", {"content": "test"})
    assert not result.success
    assert "Unknown memory type" in result.reason


def test_write_semantic_fails_below_confidence():
    result = MEMORY_BUS.write(
        "semantic",
        {"concept": "test", "description": "test", "source_episode_id": "ep1"},
        confidence=0.5,   # below new 0.75 threshold
    )
    assert not result.success
    assert "Confidence" in result.reason
    assert "0.75" in result.reason


def test_write_procedural_fails_without_verification():
    import json
    result = MEMORY_BUS.write(
        "procedural",
        {
            "skill_name": "test_skill",
            "trigger_phrase": "compile code",
            "steps_json": json.dumps([{"step": 1, "action": "run"}]),
            "trust_level": "USER_APPROVED",
        },
        confidence=0.9,
        verified=False,   # fails verification gate
    )
    assert not result.success
    assert "verification" in result.reason.lower()


def test_write_long_term_fails_without_approval():
    result = MEMORY_BUS.write(
        "long_term",
        {"partition": "General", "record": {"fact": "test"}},
        confidence=0.9,
        verified=True,
        # human_approved key is absent in data
    )
    assert not result.success
    assert "human_approved" in result.reason


def test_write_working_always_succeeds_on_valid_data():
    """Working memory has a low confidence gate (0.20) and no verification requirement."""
    result = MEMORY_BUS.write(
        "working",
        {
            "session_id": "test_session_k8",
            "trace_type": "thought",
            "content": "Testing cognitive memory bus working memory write",
        },
        confidence=0.25,  # above the new 0.20 floor
    )
    assert result.success, result.reason
    assert result.record_id is not None


# ── Read tests ─────────────────────────────────────────────────────────────────

def test_read_returns_list_of_read_results():
    results = MEMORY_BUS.read(
        "test query",
        memory_types=["working", "episodic"],
        session_id="nonexistent_session_xyz",
        limit=5,
    )
    assert isinstance(results, list)
    assert all(isinstance(r, ReadResult) for r in results)
    assert {r.memory_type for r in results} == {"working", "episodic"}


def test_read_unknown_type_returns_error_result():
    results = MEMORY_BUS.read("query", memory_types=["nonexistent_type"])
    assert len(results) == 1
    assert results[0].error is not None
    assert "No read handler" in results[0].error


def test_read_working_memory_returns_list():
    # Initialize a session so the read doesn't throw
    from backend.core.working_memory import WorkingMemory
    WorkingMemory.initialize_session("test_session_k8_read")
    WorkingMemory.log_trace(
        session_id="test_session_k8_read",
        goal_id=None,
        task_id=None,
        trace_type="thought",
        content="radar signal processing concept",
    )
    results = MEMORY_BUS.read(
        "radar",
        memory_types=["working"],
        session_id="test_session_k8_read",
    )
    assert isinstance(results, list)
    assert len(results) == 1
    assert isinstance(results[0].records, list)


def test_read_knowledge_graph_returns_list():
    results = MEMORY_BUS.read(
        "radar",
        memory_types=["knowledge_graph"],
        limit=3,
    )
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0].error is None
    assert isinstance(results[0].records, list)
