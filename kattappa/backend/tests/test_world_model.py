"""World Model Tests — Step 19 Upgrade.

Covers:
- Existing CRUD, impact, subtree, snapshot, and prediction tests (unchanged).
- Step 19: belief confidence states, causal change log, belief conflict
  detection, conflict resolution, episode cross-linking, query_world_context,
  and enriched impact_of with confidence data.
"""
from __future__ import annotations

import pytest
import time
from backend.core.world_model import WorldModel, EntityType, RelationType


@pytest.fixture(autouse=True)
def isolated_world_model(tmp_path, monkeypatch):
    # Mock runtime_data_root and config to use a local temp DB
    from backend.core.config import BackendConfig
    import backend.core.config as config_module
    import backend.core.world_model as world_model_module

    test_db = tmp_path / "kattappa_world_test.db"

    # Create isolated config
    mock_config = BackendConfig(
        root=tmp_path,
        backend_root=tmp_path,
        ollama_host="http://127.0.0.1:11434",
        model_map={},
        chroma_path=tmp_path / "chroma",
        sqlite_path=test_db,
        memory_collection="kattappa_memory",
        shell_enabled=False,
        desktop_enabled=True,
        screen_capture_enabled=False,
        guidance_overlay_enabled=True,
        teach_mode_enabled=True,
        screenshots_dir=tmp_path / "screenshots",
        audio_dir=tmp_path / "audio",
        logs_dir=tmp_path / "logs",
        workspace_dir=tmp_path / "workspace",
        hardware_profile="BALANCED",
        context_budget=4096,
    )

    monkeypatch.setattr(config_module, "load_config", lambda: mock_config)

    WorldModel.reset()
    yield test_db
    WorldModel.reset()


# ===========================================================================
# Existing Tests (unchanged) — Core CRUD, Impact, Subtree, Snapshots, Predictions
# ===========================================================================

def test_sqlite_dynamic_creation(isolated_world_model):
    conn = WorldModel._get_sqlite_conn()
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r["name"] for r in cursor.fetchall()]
    assert "world_state_nodes" in tables
    assert "world_state_edges" in tables
    assert "world_state_snapshots" in tables
    assert "world_state_predictions" in tables
    # Step 19 tables
    assert "world_belief_states" in tables
    assert "world_causal_log" in tables
    assert "world_belief_conflicts" in tables
    conn.close()


def test_crud_operations():
    WorldModel.add_entity("Radio Module", EntityType.COMPONENT, status="active", attributes={"power": "high"})
    WorldModel.add_entity("Antenna", EntityType.COMPONENT)

    ent = WorldModel.get_entity("Radio Module")
    assert ent is not None
    assert ent["name"] == "Radio Module"
    assert ent["type"] == "component"
    assert ent["status"] == "active"
    assert ent["attributes"] == {"power": "high"}

    WorldModel.add_relation("Radio Module", "Antenna", RelationType.AFFECTS)
    rels = WorldModel.relations()
    assert len(rels) == 1
    assert rels[0]["src"] == "radio module"
    assert rels[0]["dst"] == "antenna"
    assert rels[0]["relation"] == "affects"

    n = WorldModel.neighbors("Radio Module", RelationType.AFFECTS, direction="out")
    assert n == ["Antenna"]


def test_impact_and_subtree():
    WorldModel.add_entity("Project Kattappa", EntityType.PROJECT)
    WorldModel.add_entity("Cortex", EntityType.COMPONENT)
    WorldModel.add_entity("Memory Engine", EntityType.COMPONENT)
    WorldModel.add_entity("Execution Unit", EntityType.COMPONENT)
    WorldModel.add_entity("Safety Gate", EntityType.COMPONENT)

    WorldModel.add_relation("Project Kattappa", "Cortex", RelationType.CONTAINS)
    WorldModel.add_relation("Cortex", "Memory Engine", RelationType.CONTAINS)
    WorldModel.add_relation("Cortex", "Execution Unit", RelationType.AFFECTS)
    WorldModel.add_relation("Safety Gate", "Execution Unit", RelationType.DEPENDS_ON)

    tree = WorldModel.subtree("Project Kattappa")
    assert tree["name"] == "Project Kattappa"
    assert len(tree["children"]) == 1
    assert tree["children"][0]["name"] == "Cortex"
    assert tree["children"][0]["children"][0]["name"] == "Memory Engine"

    impact = WorldModel.impact_of("Cortex")
    assert "Execution Unit" in impact["affected_names"]
    assert "Safety Gate" in impact["affected_names"]


def test_snapshot_restore():
    WorldModel.add_entity("Node A", EntityType.COMPONENT, status="online",
                          confidence=0.9, confidence_state="STATED")
    WorldModel.add_entity("Node B", EntityType.COMPONENT)
    WorldModel.add_relation("Node A", "Node B", RelationType.AFFECTS)

    WorldModel.create_snapshot("snap1")

    WorldModel.add_entity("Node C", EntityType.COMPONENT)
    WorldModel.add_relation("Node B", "Node C", RelationType.AFFECTS)

    assert len(WorldModel.entities()) == 3

    WorldModel.restore_snapshot("snap1")

    ents = WorldModel.entities()
    assert len(ents) == 2
    assert any(e["name"] == "Node A" for e in ents)
    assert any(e["name"] == "Node B" for e in ents)
    assert not any(e["name"] == "Node C" for e in ents)

    # Belief states should also be restored
    beliefs = WorldModel.get_belief_state("Node A")
    assert any(b["attribute"] == "status" and b["value"] == "online" for b in beliefs)


def test_predictions_log():
    WorldModel.record_prediction(
        prediction_id="pred_1",
        action="DEPLOY",
        predicted_success=0.85,
        predicted_cost=15.0,
        predicted_time="2 hours",
        confidence_interval=(0.75, 0.92),
        risk_score=0.18,
    )

    pred = WorldModel.get_prediction("pred_1")
    assert pred is not None
    assert pred["action"] == "DEPLOY"
    assert pred["predicted_success"] == 0.85
    assert pred["predicted_cost"] == 15.0
    assert pred["predicted_time"] == "2 hours"
    assert pred["confidence_interval"] == (0.75, 0.92)
    assert pred["risk_score"] == 0.18

    preds = WorldModel.list_predictions()
    assert len(preds) == 1


# ===========================================================================
# Step 19 Tests — Belief Confidence States, Causal Log, Conflict Queue
# ===========================================================================

def test_belief_confidence_states():
    """Verify that add_entity writes a belief state record with correct confidence."""
    WorldModel.add_entity(
        "Radar Array",
        EntityType.COMPONENT,
        status="operational",
        confidence=0.9,
        confidence_state="STATED",
        source_episode_id="ep_radar_001",
    )

    beliefs = WorldModel.get_belief_state("Radar Array")
    assert len(beliefs) >= 1

    status_belief = next((b for b in beliefs if b["attribute"] == "status"), None)
    assert status_belief is not None
    assert status_belief["value"] == "operational"
    assert status_belief["confidence"] == 0.9
    assert status_belief["confidence_state"] == "STATED"
    assert status_belief["source_episode_id"] == "ep_radar_001"


def test_causal_log_on_add_entity():
    """Verify that adding an entity creates an ENTITY_ADDED causal log entry."""
    WorldModel.add_entity(
        "Sensor Hub",
        EntityType.DEVICE,
        status="idle",
        source_episode_id="ep_sensor_001",
        changed_by="user",
    )

    log = WorldModel.get_causal_log("Sensor Hub")
    assert len(log) >= 1
    assert log[0]["change_type"] == "ENTITY_ADDED"
    assert "Sensor Hub" in log[0]["description"]
    assert log[0]["source_episode_id"] == "ep_sensor_001"
    assert log[0]["changed_by"] == "user"


def test_causal_log_on_status_update():
    """Verify that updating entity status writes a STATUS_CHANGED causal log entry."""
    WorldModel.add_entity("Power Bus", EntityType.COMPONENT, status="standby",
                          confidence_state="STATED")

    updated = WorldModel.update_entity_status(
        "Power Bus",
        "active",
        confidence=0.95,
        confidence_state="CONFIRMED",
        source_episode_id="ep_power_switch",
        changed_by="system",
    )
    assert updated is True

    log = WorldModel.get_causal_log("Power Bus")
    change_types = [e["change_type"] for e in log]
    assert "STATUS_CHANGED" in change_types

    status_log = next(e for e in log if e["change_type"] == "STATUS_CHANGED")
    assert "standby" in status_log["description"]
    assert "active" in status_log["description"]
    assert status_log["source_episode_id"] == "ep_power_switch"

    # Verify entity node is also updated
    ent = WorldModel.get_entity("Power Bus")
    assert ent["status"] == "active"


def test_belief_conflict_detection():
    """Verify that a weaker contradicting belief update is routed to the conflict queue."""
    # Add entity with CONFIRMED (strongest) status
    WorldModel.add_entity(
        "Firewall Node",
        EntityType.COMPONENT,
        status="active",
        confidence=0.95,
        confidence_state="CONFIRMED",
    )

    # Try to update with INFERRED (weaker) — should be routed to conflict queue
    updated = WorldModel.update_entity_status(
        "Firewall Node",
        "degraded",
        confidence=0.4,
        confidence_state="INFERRED",
    )
    assert updated is False  # Should NOT have applied the weaker evidence

    # Verify the conflict was queued
    conflicts = WorldModel.list_conflicts(resolution_state="PENDING")
    assert len(conflicts) >= 1
    conflict = next(
        c for c in conflicts if c["entity_id"] == "firewall node" and c["attribute"] == "status"
    )
    assert conflict["old_value"] == "active"
    assert conflict["new_value"] == "degraded"
    assert conflict["resolution_state"] == "PENDING"

    # Original belief should be unchanged
    ent = WorldModel.get_entity("Firewall Node")
    assert ent["status"] == "active"


def test_resolve_conflict():
    """Verify that resolving a conflict with RESOLVED_NEW applies the new value."""
    WorldModel.add_entity(
        "Routing Engine",
        EntityType.COMPONENT,
        status="online",
        confidence=0.7,
        confidence_state="INFERRED",
    )

    # Generate a conflict: INFERRED vs lower INFERRED with same confidence
    WorldModel.update_entity_status(
        "Routing Engine",
        "offline",
        confidence=0.5,
        confidence_state="INFERRED",
    )

    conflicts = WorldModel.list_conflicts(resolution_state="PENDING")
    routing_conflict = next(
        (c for c in conflicts if c["entity_id"] == "routing engine"), None
    )
    assert routing_conflict is not None

    # Resolve by accepting the new value
    resolved = WorldModel.resolve_conflict(routing_conflict["conflict_id"], "RESOLVED_NEW")
    assert resolved is True

    # Verify conflict is resolved
    still_pending = [
        c for c in WorldModel.list_conflicts(resolution_state="PENDING")
        if c["conflict_id"] == routing_conflict["conflict_id"]
    ]
    assert len(still_pending) == 0

    resolved_list = WorldModel.list_conflicts(resolution_state="RESOLVED_NEW")
    assert any(c["conflict_id"] == routing_conflict["conflict_id"] for c in resolved_list)

    # Verify the entity status was updated
    ent = WorldModel.get_entity("Routing Engine")
    assert ent["status"] == "offline"


def test_causal_log_episode_cross_link():
    """Verify that source_episode_id is preserved in the causal log for retrieval."""
    WorldModel.add_entity(
        "Navigation Unit",
        EntityType.COMPONENT,
        status="calibrating",
        source_episode_id="ep_nav_init_42",
        changed_by="deployment_agent",
    )

    WorldModel.add_entity("GPS Receiver", EntityType.COMPONENT)
    WorldModel.add_relation(
        "Navigation Unit",
        "GPS Receiver",
        RelationType.DEPENDS_ON,
        source_episode_id="ep_nav_init_42",
    )

    # Causal log for entity add
    entity_log = WorldModel.get_causal_log("Navigation Unit")
    ep_linked = [e for e in entity_log if e.get("source_episode_id") == "ep_nav_init_42"]
    assert len(ep_linked) >= 1

    # Causal log for relation add (stored under src entity)
    relation_log = WorldModel.get_causal_log("Navigation Unit")
    relation_entries = [e for e in relation_log if e["change_type"] == "RELATION_ADDED"]
    assert len(relation_entries) >= 1
    assert relation_entries[0]["source_episode_id"] == "ep_nav_init_42"


def test_query_world_context():
    """Verify that query_world_context returns relevant entities with belief and causal data."""
    WorldModel.add_entity(
        "Radar Processor",
        EntityType.COMPONENT,
        status="active",
        confidence=0.85,
        confidence_state="OBSERVED",
        source_episode_id="ep_radar_setup",
    )
    WorldModel.add_entity(
        "Signal Filter",
        EntityType.COMPONENT,
        status="active",
    )
    # Add a causal edge so Signal Filter is a 1-hop neighbor of Radar Processor
    WorldModel.add_relation("Radar Processor", "Signal Filter", RelationType.AFFECTS)

    # Add an unrelated entity that should NOT appear
    WorldModel.add_entity("Battery Pack", EntityType.RESOURCE, status="charging")

    results = WorldModel.query_world_context("radar", limit=10)
    result_names = [r["name"] for r in results]

    # Direct match
    assert "Radar Processor" in result_names
    # 1-hop neighbor via AFFECTS edge
    assert "Signal Filter" in result_names
    # Unrelated entity should not appear
    assert "Battery Pack" not in result_names

    # Verify belief and causal provenance included
    radar_result = next(r for r in results if r["name"] == "Radar Processor")
    assert radar_result["confidence"] == pytest.approx(0.85)
    assert radar_result["confidence_state"] == "OBSERVED"
    assert len(radar_result["belief_states"]) >= 1
    assert len(radar_result["causal_log"]) >= 1
    assert radar_result["is_direct_match"] is True

    signal_result = next(r for r in results if r["name"] == "Signal Filter")
    assert signal_result["is_direct_match"] is False


def test_impact_of_with_confidence():
    """Verify that impact_of includes confidence and confidence_state in affected entries."""
    WorldModel.add_entity("STM32", EntityType.COMPONENT, status="running",
                          confidence=0.9, confidence_state="CONFIRMED")
    WorldModel.add_entity("Firmware", EntityType.COMPONENT, status="loaded",
                          confidence=0.75, confidence_state="OBSERVED")
    WorldModel.add_entity("Safety Monitor", EntityType.COMPONENT)

    WorldModel.add_relation("STM32", "Firmware", RelationType.AFFECTS)
    WorldModel.add_entity("Logger", EntityType.COMPONENT)
    WorldModel.add_relation("Logger", "STM32", RelationType.DEPENDS_ON)

    impact = WorldModel.impact_of("STM32")

    # All affected entries should include confidence data
    for entry in impact["affected"]:
        assert "confidence" in entry
        assert "confidence_state" in entry
        assert 0.0 <= entry["confidence"] <= 1.0

    # Check that Firmware specifically carries its belief confidence
    firmware_entry = next(
        (e for e in impact["affected"] if e["entity"] == "Firmware"), None
    )
    assert firmware_entry is not None
    assert firmware_entry["confidence"] == pytest.approx(0.75)
    assert firmware_entry["confidence_state"] == "OBSERVED"
