"""Tests for Phase K13: Knowledge Graph Sync and Decay Scheduler."""
from __future__ import annotations

import time
import math
import pytest
from datetime import datetime, timezone
from backend.core.graph import _get_kg
from backend.core.knowledge_graph import KGNode, EntityType
from backend.core.kg_scheduler import KGSyncScheduler, start_kg_scheduler, stop_kg_scheduler


@pytest.fixture(autouse=True)
def cleanup_scheduler():
    yield
    try:
        stop_kg_scheduler()
    except Exception:
        pass


def test_kg_nodes_carry_k13_attributes():
    kg = _get_kg()
    assert kg is not None

    node_name = "K13_Test_Node"
    # Create node with K13 properties
    node = kg.add_node(
        name=node_name,
        entity_type=EntityType.CONCEPT,
        confidence=0.9,
        belief_state="BELIEVED",
        evidence=["source_doc_a", "source_doc_b"],
        last_verified_at=datetime.now(timezone.utc).isoformat()
    )

    assert node.name == node_name
    assert node.belief_state == "BELIEVED"
    assert "source_doc_a" in node.evidence
    assert node.last_verified_at is not None

    # Retrieve from database and verify it carries the properties
    retrieved = kg.resolve_entity(node_name)
    assert retrieved is not None
    assert retrieved.name == node_name
    assert retrieved.belief_state == "BELIEVED"
    assert "source_doc_b" in retrieved.evidence


def test_temporal_confidence_decay():
    kg = _get_kg()
    assert kg is not None

    node_name = "Decayable_Node"
    # Create a node with a past updated_at timestamp
    node = kg.add_node(
        name=node_name,
        entity_type=EntityType.CONCEPT,
        confidence=1.0,
        belief_state="BELIEVED"
    )

    # Directly adjust the node's updated_at back by 10 days (864000 seconds) in SQLite
    past_time = datetime.now(timezone.utc).timestamp() - 864000
    past_iso = datetime.fromtimestamp(past_time, timezone.utc).isoformat()
    
    with kg._store._lock:
        conn = kg._store._get_conn()
        conn.execute("UPDATE kg_nodes SET updated_at = ? WHERE id = ?", (past_iso, node.id))
        conn.commit()
        conn.close()

    # Decay rate equivalent to half life of ~7 days: lambda = 1.15e-6
    # For 10 days decay: 1.0 * e^(-1.15e-6 * 864000) = e^(-0.9936) approx 0.37
    current_now = datetime.now(timezone.utc).timestamp()
    decayed_count = kg.decay_unrefreshed_nodes(decay_rate=1.15e-6, now=current_now)
    assert decayed_count > 0

    # Read node back and assert confidence decayed
    decayed_node = kg.resolve_entity(node_name)
    assert decayed_node is not None
    assert decayed_node.confidence < 0.90
    assert decayed_node.confidence > 0.10
    # Decayed value is around 0.37
    assert pytest.approx(decayed_node.confidence, abs=0.1) == 0.37
    assert decayed_node.belief_state == "BELIEVED"  # still believed since confidence > 0.20


def test_temporal_confidence_decay_to_hypothetical():
    kg = _get_kg()
    assert kg is not None

    node_name = "Deep_Decay_Node"
    # Create a node with a past updated_at timestamp (e.g. 25 days ago)
    node = kg.add_node(
        name=node_name,
        entity_type=EntityType.CONCEPT,
        confidence=1.0,
        belief_state="BELIEVED"
    )

    past_time = datetime.now(timezone.utc).timestamp() - (25 * 86400)
    past_iso = datetime.fromtimestamp(past_time, timezone.utc).isoformat()
    
    with kg._store._lock:
        conn = kg._store._get_conn()
        conn.execute("UPDATE kg_nodes SET updated_at = ? WHERE id = ?", (past_iso, node.id))
        conn.commit()
        conn.close()

    current_now = datetime.now(timezone.utc).timestamp()
    kg.decay_unrefreshed_nodes(decay_rate=1.15e-6, now=current_now)

    decayed_node = kg.resolve_entity(node_name)
    assert decayed_node is not None
    # 25 days decay: 1.0 * e^(-1.15e-6 * 25 * 86400) = e^(-2.484) approx 0.083 < 0.20
    assert decayed_node.confidence < 0.20
    # Since confidence fell below 0.20, state manager transitions it to HYPOTHETICAL
    assert decayed_node.belief_state == "HYPOTHETICAL"


def test_scheduler_manual_trigger():
    scheduler = KGSyncScheduler(interval_seconds=600)
    # Ensure manual trigger runs without issues
    scheduler.trigger_sync()
    
    # Start and stop scheduler to verify thread lifecycle
    scheduler.start()
    assert scheduler._thread is not None
    assert scheduler._thread.is_alive()
    scheduler.stop()
    assert scheduler._thread is None
