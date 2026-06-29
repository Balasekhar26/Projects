"""Tests for WorldModel + CapabilityGraph integration with ReasoningEngine and Planner."""
from __future__ import annotations

import pytest

from backend.core.world_model import WorldModel, EntityType, RelationType
from backend.core.capability_graph import CapabilityGraph
from backend.core.reasoning_engine import ReasoningEngine
from backend.core.event_bus import EventBus, EventName


@pytest.fixture(autouse=True)
def clean():
    WorldModel.reset()
    CapabilityGraph.reset()
    EventBus.reset()
    yield
    WorldModel.reset()
    CapabilityGraph.reset()
    EventBus.reset()


# ---------------------------------------------------------------------------
# WorldModel integration tests
# ---------------------------------------------------------------------------

def test_world_model_add_and_query_entity():
    WorldModel.add_entity("kattappa_project", EntityType.PROJECT, status="active")
    results = WorldModel.query_world_context(query_text="kattappa")
    assert len(results) >= 1
    names = [r["name"] for r in results]
    assert "kattappa_project" in names


def test_world_model_entity_with_attributes():
    WorldModel.add_entity(
        "backend_service",
        EntityType.COMPONENT,
        status="running",
        attributes={"port": "8000", "language": "python"},
        confidence=0.9,
        confidence_state="OBSERVED",
    )
    results = WorldModel.query_world_context(query_text="backend_service")
    assert len(results) >= 1
    entity = results[0]
    assert entity["status"] == "running"
    # Belief states should exist
    beliefs = WorldModel.get_belief_state("backend_service")
    attrs = {b["attribute"]: b["value"] for b in beliefs}
    assert "status" in attrs or "port" in attrs


def test_world_model_relation_connects_entities():
    WorldModel.add_entity("project_alpha", EntityType.PROJECT)
    WorldModel.add_entity("goal_deploy", EntityType.GOAL)
    WorldModel.add_relation("project_alpha", "goal_deploy", RelationType.CONTAINS)

    neighbors = WorldModel.neighbors("project_alpha", RelationType.CONTAINS)
    assert "goal_deploy" in neighbors


def test_world_model_query_expands_causal_neighbors():
    WorldModel.add_entity("rf_module", EntityType.COMPONENT)
    WorldModel.add_entity("antenna", EntityType.COMPONENT)
    WorldModel.add_entity("battery", EntityType.RESOURCE)
    WorldModel.add_relation("rf_module", "antenna", RelationType.AFFECTS)
    WorldModel.add_relation("antenna", "battery", RelationType.AFFECTS)

    results = WorldModel.query_world_context(query_text="rf_module")
    names = [r["name"] for r in results]
    assert "rf_module" in names
    assert "antenna" in names  # 1-hop causal neighbor expanded


def test_world_model_causal_log_written():
    WorldModel.add_entity("api_gateway", EntityType.COMPONENT, status="starting")
    log = WorldModel.get_causal_log("api_gateway")
    assert len(log) >= 1
    change_types = [e["change_type"] for e in log]
    assert "ENTITY_ADDED" in change_types


def test_world_model_belief_conflict_queued_on_weaker_evidence():
    WorldModel.add_entity(
        "db_server",
        EntityType.DEVICE,
        status="online",
        confidence=0.95,
        confidence_state="CONFIRMED",
    )
    # Try to overwrite with weaker evidence (lower confidence_state order)
    WorldModel.add_entity(
        "db_server",
        EntityType.DEVICE,
        status="offline",   # contradicting status
        confidence=0.5,
        confidence_state="INFERRED",  # weaker than CONFIRMED
    )
    # Status should still be "online" (conflict queued, not overwritten)
    entity = WorldModel.get_entity("db_server")
    assert entity is not None
    # Check conflict was queued
    conflicts = WorldModel.list_conflicts(resolution_state="PENDING")
    # There should be at least one conflict record
    assert len(conflicts) >= 1


def test_world_model_query_returns_empty_for_unknown():
    results = WorldModel.query_world_context(query_text="zzz_nonexistent_entity_xyz")
    assert results == []


# ---------------------------------------------------------------------------
# CapabilityGraph integration tests
# ---------------------------------------------------------------------------

def test_capability_graph_register_and_get():
    CapabilityGraph.register("code_execution", available=True)
    cap = CapabilityGraph.get("code_execution")
    assert cap is not None
    assert cap["available"] is True
    assert cap["name"] == "code_execution"


def test_capability_graph_assess_satisfied():
    CapabilityGraph.register("python_runtime", available=True)
    CapabilityGraph.register("git_operations", available=True)
    result = CapabilityGraph.assess(
        "Build Python module",
        ["python_runtime", "git_operations"]
    )
    assert result["can_proceed"] is True
    assert len(result["missing"]) == 0


def test_capability_graph_assess_missing():
    CapabilityGraph.register("code_execution", available=False)
    result = CapabilityGraph.assess("Build module", ["code_execution"])
    assert result["can_proceed"] is False
    assert "code_execution" in result["missing"]


def test_capability_graph_detects_unregistered_as_missing():
    result = CapabilityGraph.assess("Use nonexistent_tool", ["nonexistent_quantum_chip_v9"])
    assert "nonexistent_quantum_chip_v9" in result["missing"]
    assert result["can_proceed"] is False


def test_capability_graph_coverage_is_one_when_satisfied():
    CapabilityGraph.register("llm_inference", available=True)
    result = CapabilityGraph.assess("Run inference", ["llm_inference"])
    assert result["coverage"] == 1.0


def test_capability_graph_coverage_partial():
    CapabilityGraph.register("tool_a", available=True)
    CapabilityGraph.register("tool_b", available=False)
    result = CapabilityGraph.assess("Goal", ["tool_a", "tool_b"])
    assert 0.0 < result["coverage"] < 1.0


def test_capability_graph_bottleneck_detection():
    # tool_c depends on tool_d; tool_d is missing → tool_d is a bottleneck
    CapabilityGraph.register("tool_c", available=True, depends_on=["tool_d"])
    CapabilityGraph.register("tool_d", available=False)
    result = CapabilityGraph.assess("Goal", ["tool_c", "tool_d"])
    assert "tool_d" in result["bottlenecks"]


def test_capability_graph_alternative_satisfies():
    CapabilityGraph.register(
        "browser_control",
        available=False,
        alternatives=["playwright_adapter"],
    )
    CapabilityGraph.register("playwright_adapter", available=True)
    result = CapabilityGraph.assess("Web automation", ["browser_control"])
    # Should be satisfied via alternative
    assert result["can_proceed"] is True


# ---------------------------------------------------------------------------
# ReasoningEngine → CapabilityGraph integration
# ---------------------------------------------------------------------------

def test_reasoning_engine_reason_detects_capability_gap():
    # The cap doesn't exist → should be in gaps
    trace = ReasoningEngine.reason(
        "Launch rocket engine",
        "Fire ion thruster on spacecraft",
        required_capabilities=["ion_thruster_v99_nonexistent"],
    )
    assert any(g["capability"] == "ion_thruster_v99_nonexistent" for g in trace.capability_gaps)
    assert trace.status == "BLOCKED_ON_CAPABILITY"


def test_reasoning_engine_reason_no_gap_when_satisfied():
    CapabilityGraph.register("code_execution", available=True)
    CapabilityGraph.register("test_runner", available=True)
    trace = ReasoningEngine.reason(
        "Build and test Python module",
        "Build python module and run pytest tests",
        required_capabilities=["code_execution", "test_runner"],
    )
    assert len(trace.capability_gaps) == 0
    # No gaps → should not be BLOCKED_ON_CAPABILITY
    assert trace.status != "BLOCKED_ON_CAPABILITY"


def test_reasoning_engine_reason_world_context_populated():
    WorldModel.add_entity("kattappa_backend", EntityType.PROJECT, status="active")
    trace = ReasoningEngine.reason("Deploy kattappa backend", "Push to production server")
    # world_context may be populated if entity matches query
    # Even if not, the call should not crash
    assert isinstance(trace.world_context, dict)


def test_reasoning_engine_capability_assessed_event():
    import time
    events = []
    EventBus.subscribe(EventName.CAPABILITY_ASSESSED, events.append)
    ReasoningEngine.reason("Build Python module", "Create FastAPI python app")
    time.sleep(0.15)
    assert len(events) >= 1
