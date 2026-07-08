"""Integration tests for Program 4: World State & Event System (WSE).
"""
from __future__ import annotations

import os
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from backend.core.ledger.models.enums import EventType
from backend.core.ledger.models.event import LedgerEvent
from backend.core.wse.event_bus import WSEEventBus
from backend.core.wse.coordinator import WSECoordinator
from backend.core.wse.observation import Observation
from backend.core.wse.state_transition import StateTransition
from backend.core.wse.timeline import WSETimeline
from backend.core.wse.world_diff import WSEWorldDiff


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def wse_test_env():
    """Initializes a isolated testing DB for WSE event bus."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    # Reset/instantiate test bus
    bus = WSEEventBus.reset_instance(db_path=db_path)
    coordinator = WSECoordinator(bus=bus)

    yield coordinator

    # Clean up test database
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_observation_model_factory():
    """Validates the Observation factory and model methods."""
    obs = Observation.create(
        source="sensor_01",
        subject="temperature",
        predicate="room_temp",
        value=24.5,
        confidence=0.95,
        session_id="session_123",
        goal_id="goal_abc",
        metadata={"unit": "Celsius"}
    )
    assert obs.observation_id.startswith("obs_")
    assert obs.source == "sensor_01"
    assert obs.subject == "temperature"
    assert obs.predicate == "room_temp"
    assert obs.value == 24.5
    assert obs.confidence == 0.95
    assert obs.session_id == "session_123"
    assert obs.goal_id == "goal_abc"
    assert obs.metadata == {"unit": "Celsius"}

    # Round trip dict serialization
    d = obs.to_dict()
    obs_copy = Observation.from_dict(d)
    assert obs == obs_copy


def test_state_transition_model_factory():
    """Validates the StateTransition factory and serialization."""
    trans = StateTransition.create(
        entity_id="light_01",
        entity_type="device",
        from_state={"power": "off"},
        to_state={"power": "on", "brightness": 100},
        trigger_event_id="evt_trigger_456",
        actor="user_agent",
        session_id="sess_abc",
        goal_id="goal_xyz",
        reason="User requested light switch",
        metadata={"manual": True}
    )
    assert trans.transition_id.startswith("trans_")
    assert trans.entity_id == "light_01"
    assert trans.entity_type == "device"
    assert trans.from_state == {"power": "off"}
    assert trans.to_state == {"power": "on", "brightness": 100}
    assert trans.trigger_event_id == "evt_trigger_456"
    assert trans.actor == "user_agent"
    assert trans.reason == "User requested light switch"

    d = trans.to_dict()
    trans_copy = StateTransition.from_dict(d)
    assert trans == trans_copy


def test_event_bus_publishing_and_subscriptions(wse_test_env):
    """Verifies event publication and subscriber dispatching, including wildcards."""
    coordinator = wse_test_env
    bus = coordinator.bus

    received_events = []
    wildcard_events = []

    def sub_callback(topic, event):
        received_events.append(event)

    def wildcard_callback(topic, event):
        wildcard_events.append(event)

    bus.subscribe(EventType.OBSERVATION_RECORDED.value, sub_callback)
    bus.subscribe("*", wildcard_callback)

    # Emit an observation event
    obs = coordinator.record_observation(
        source="subsystem_test",
        subject="host_01",
        predicate="cpu",
        value=42,
    )

    assert len(received_events) == 1
    assert received_events[0].payload["observation_id"] == obs.observation_id
    assert len(wildcard_events) == 1
    assert wildcard_events[0].payload["observation_id"] == obs.observation_id

    # Emit a different event (should only hit wildcard)
    trans = coordinator.record_transition(
        entity_id="entity_01",
        entity_type="concept",
        from_state={"active": False},
        to_state={"active": True},
    )

    assert len(received_events) == 1  # unchanged
    assert len(wildcard_events) == 2
    assert wildcard_events[1].payload["transition_id"] == trans.transition_id


def test_isolated_subscriber_errors(wse_test_env):
    """Verifies that an error in one subscriber does not halt others or publishers."""
    coordinator = wse_test_env
    bus = coordinator.bus

    good_subscriber_received = []

    def bad_callback(topic, event):
        raise RuntimeError("Something went wrong!")

    def good_callback(topic, event):
        good_subscriber_received.append(event)

    bus.subscribe(EventType.OBSERVATION_RECORDED.value, bad_callback)
    bus.subscribe(EventType.OBSERVATION_RECORDED.value, good_callback)

    # Should not raise exception
    obs = coordinator.record_observation(
        source="test",
        subject="sub",
        predicate="pred",
        value="val",
    )

    assert len(good_subscriber_received) == 1
    assert good_subscriber_received[0].payload["observation_id"] == obs.observation_id


def test_timeline_at_reconstruction(wse_test_env):
    """Tests reconstructing state snapshots using WSETimeline.at(T)."""
    coordinator = wse_test_env
    timeline = coordinator.timeline

    # Record transitions for a light over time
    t0 = time.time()
    
    # 1. Light switches on
    time.sleep(0.01)
    t1 = time.time()
    coordinator.record_transition(
        entity_id="device_light",
        entity_type="light",
        from_state={"status": "off"},
        to_state={"status": "on", "level": 80},
    )

    # 2. Level increases
    time.sleep(0.01)
    t2 = time.time()
    coordinator.record_transition(
        entity_id="device_light",
        entity_type="light",
        from_state={"status": "on", "level": 80},
        to_state={"status": "on", "level": 100},
    )

    # 3. Thermostat gets updated
    time.sleep(0.01)
    t3 = time.time()
    coordinator.record_transition(
        entity_id="thermostat",
        entity_type="climate",
        from_state={"temp": 20},
        to_state={"temp": 22},
    )

    # Query t0 (everything empty)
    state_t0 = timeline.at(t0)
    assert "device_light" not in state_t0
    assert "thermostat" not in state_t0

    # Query t1 (light is on/80, no thermostat)
    state_t1 = timeline.at(t1 + 0.001)
    assert state_t1["device_light"] == {"status": "on", "level": 80}
    assert "thermostat" not in state_t1

    # Query t2 (light is 100)
    state_t2 = timeline.at(t2 + 0.001)
    assert state_t2["device_light"] == {"status": "on", "level": 100}

    # Query t3 (both light and thermostat are present)
    state_t3 = timeline.at(t3 + 0.001)
    assert state_t3["device_light"] == {"status": "on", "level": 100}
    assert state_t3["thermostat"] == {"temp": 22}


def test_timeline_history_of(wse_test_env):
    """Verifies WSETimeline.history_of(entity_id)."""
    coordinator = wse_test_env
    timeline = coordinator.timeline

    coordinator.record_transition("ent_A", "concept", {}, {"val": 1})
    coordinator.record_transition("ent_B", "concept", {}, {"val": 99})
    coordinator.record_transition("ent_A", "concept", {"val": 1}, {"val": 2})

    history_A = timeline.history_of("ent_A")
    assert len(history_A) == 2
    assert history_A[0].to_state == {"val": 1}
    assert history_A[1].to_state == {"val": 2}

    history_B = timeline.history_of("ent_B")
    assert len(history_B) == 1
    assert history_B[0].to_state == {"val": 99}


def test_timeline_last_observation_of(wse_test_env):
    """Verifies WSETimeline.last_observation_of()."""
    coordinator = wse_test_env
    timeline = coordinator.timeline

    coordinator.record_observation("source", "battery", "level", 95)
    time.sleep(0.01)
    coordinator.record_observation("source", "battery", "level", 94)

    last_obs = timeline.last_observation_of("battery", "level")
    assert last_obs is not None
    assert last_obs.value == 94


def test_world_diff_generation(wse_test_env):
    """Tests generating a world state difference between two timestamps."""
    coordinator = wse_test_env

    t_start = time.time()
    
    # Init state: server_01 is inactive
    coordinator.record_transition("server_01", "compute", {}, {"status": "inactive"})
    time.sleep(0.01)
    t_checkpoint = time.time()

    # Step 2: server_01 goes online, database_01 is created
    time.sleep(0.01)
    coordinator.record_transition("server_01", "compute", {"status": "inactive"}, {"status": "active"})
    coordinator.record_transition("database_01", "db", {}, {"connection_count": 0})
    time.sleep(0.01)
    t_end = time.time()

    # Compute diff between checkpoint and end
    report = coordinator.diff(t_checkpoint, t_end)
    assert "database_01" in report.added
    assert not report.removed
    
    changed_ids = [c["entity_id"] for c in report.changed]
    assert "server_01" in changed_ids
    
    server_change = [c for c in report.changed if c["entity_id"] == "server_01"][0]
    assert server_change["changes"]["status"] == {"from": "inactive", "to": "active"}


def test_ecl_event_emission():
    """Mocks and tests that the ECLCoordinator triggers event emissions."""
    mock_decomp = {"goal_id": "test_goal_123", "registered_nodes": []}
    mock_budget = {"micro_batch_size": 2}
    mock_sim = {"best_branch_id": "branch_0", "viability_score": 0.9}
    mock_routing = {"model": "fast"}
    mock_task_graph = MagicMock()
    mock_task_graph.is_finished.return_value = True

    # Patch modules called within ECLCoordinator
    with patch("backend.core.ecl.coordinator.ECLGoalDecomposer.decompose", return_value=mock_decomp), \
         patch("backend.core.ecl.coordinator.ECLBudgetManager.calculate_budget", return_value=mock_budget), \
         patch("backend.core.ecl.coordinator.ECLPolicyEngine.validate_plan", return_value=(True, "")), \
         patch("backend.core.ecl.coordinator.ECLSimulationRunner.evaluate_viability", return_value=mock_sim), \
         patch("backend.core.ecl.coordinator.ECLRouter.route_task", return_value=mock_routing), \
         patch("backend.core.ecl.coordinator.TaskGraph", return_value=mock_task_graph), \
         patch("backend.core.ecl.coordinator.TaskScheduler") as mock_sched_cls, \
         patch("backend.core.ecl.coordinator.GoalHierarchy") as mock_goal_hierarchy, \
         patch("backend.core.wse.event_bus.WSEEventBus.publish") as mock_publish:

        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        
        # Trigger plan_and_execute
        from backend.core.ecl.coordinator import ECLCoordinator
        ECLCoordinator.plan_and_execute("Test Goal Title", "Description")

        # Verify publish was invoked twice (ECL_GOAL_DECOMPOSED + ECL_PLAN_EXECUTED)
        assert mock_publish.call_count == 2
        calls = [c[0][0] for c in mock_publish.call_args_list]
        event_types = [e.event_type for e in calls]
        assert EventType.ECL_GOAL_DECOMPOSED in event_types
        assert EventType.ECL_PLAN_EXECUTED in event_types


def test_mce_event_emission():
    """Mocks and tests that the MCEConsolidationEngine triggers event emissions."""
    mock_dedup = MagicMock()
    mock_dedup.unique_ids = ["ep_01"]
    mock_dedup.unique_count = 1
    mock_dedup.exact_dupe_count = 0
    mock_dedup.near_dupe_count = 0

    mock_promotion = MagicMock()
    mock_promotion.promoted_ids = ["ep_01"]
    mock_promotion.promoted_count = 1
    mock_promotion.rejected_count = 0

    mock_integration = MagicMock()
    mock_integration.nodes_added = 2
    mock_integration.relations_added = 1
    mock_integration.errors = 0

    mock_archive = MagicMock()
    mock_archive.archived_count = 0
    mock_archive.total_scanned = 1

    with patch("backend.core.mce.consolidation_engine.MCEDuplicateDetector.detect", return_value=mock_dedup), \
         patch("backend.core.mce.consolidation_engine.MCEImportanceScorer.score_episodes", return_value=[]), \
         patch("backend.core.mce.consolidation_engine.MCEEpisodicPromoter.promote", return_value=mock_promotion), \
         patch("backend.core.mce.consolidation_engine.MCESemanticExtractor.extract", return_value=[]), \
         patch("backend.core.mce.consolidation_engine.MCEArchiveManager.archive_stale", return_value=mock_archive), \
         patch("backend.core.wse.event_bus.WSEEventBus.publish") as mock_publish:

        from backend.core.mce.consolidation_engine import MCEConsolidationEngine
        MCEConsolidationEngine.run_cycle()

        assert mock_publish.call_count == 1
        event = mock_publish.call_args[0][0]
        assert event.event_type == EventType.MCE_CYCLE_COMPLETED
        assert event.payload["success"] is True
