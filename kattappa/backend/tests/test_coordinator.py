"""Tests for Phase K22: World Model Coordinator."""
from __future__ import annotations

import pytest
from backend.core.cos.coordinator import WorldModelCoordinator
from backend.core.cos.entity_system import SelfEntity, EconomicEntity


@pytest.fixture(autouse=True)
def setup_coordinator():
    WorldModelCoordinator.reset()


def test_entity_retrieval_and_registration():
    # Create SelfEntity representing active runtime properties
    entity = SelfEntity(entity_id="kattappa_kernel", canonical_id="self.core.kattappa", entity_type="self", cpu_load=0.2)
    entity.properties["cpu_load"] = 0.2
    WorldModelCoordinator.register_entity("self", entity)

    # Retrieve and verify
    retrieved = WorldModelCoordinator.get_entity("self", "kattappa_kernel")
    assert retrieved is not None
    assert retrieved.entity_id == "kattappa_kernel"
    assert retrieved.canonical_id == "self.core.kattappa"


def test_simulation_branching_and_isolation():
    entity = SelfEntity(entity_id="kattappa_kernel", canonical_id="self.core.kattappa", entity_type="self", cpu_load=0.2)
    entity.properties["cpu_load"] = 0.2
    WorldModelCoordinator.register_entity("self", entity)

    # Create simulation branch
    branch_id = WorldModelCoordinator.create_branch("main")

    # Modify branch entity
    branch_entity = WorldModelCoordinator.get_entity("self", "kattappa_kernel", branch_id)
    assert branch_entity is not None
    branch_entity.properties["cpu_load"] = 0.9

    # Verify isolation
    parent_entity = WorldModelCoordinator.get_entity("self", "kattappa_kernel", "main")
    assert parent_entity.properties.get("cpu_load") == 0.2
    assert branch_entity.properties.get("cpu_load") == 0.9


def test_simulate_action_and_proposed_merge():
    # Setup self entity with cpu_load
    entity = SelfEntity(entity_id="kattappa_kernel", canonical_id="self.core.kattappa", entity_type="self", cpu_load=0.2)
    entity.properties["cpu_load"] = 0.2
    WorldModelCoordinator.register_entity("self", entity)

    branch_id = WorldModelCoordinator.create_branch("main")

    # Simulate CPU degradation action on branch
    action = {"type": "degrade_cpu"}
    res = WorldModelCoordinator.simulate_action(branch_id, action)

    assert res.success is True
    assert res.predicted_states["kattappa_kernel.cpu_load"] == 0.95
    assert res.effects["cpu"] == "degraded"

    # Propose merge and verify delta events generated
    proposed_events = WorldModelCoordinator.propose_merge(branch_id)
    assert len(proposed_events) == 1


def test_bayesian_branch_merge():
    # Setup economic budget
    entity = EconomicEntity(entity_id="compute_wallet", canonical_id="wallet.compute", entity_type="economic", cost_per_query=0.5)
    entity.properties["cost_per_query"] = 0.5
    WorldModelCoordinator.register_entity("economic", entity)

    # Create prior belief in parent registry belief engine
    parent_rev = WorldModelCoordinator._revision_engines["main"]
    from backend.core.cos.state_representation import EvidenceSource, PropertyValue
    src = EvidenceSource(name="initial_db", source_type="user", reliability=0.9)
    # We set prior confidence to 0.50 so that the simulation evidence overrides it
    pv_prior = PropertyValue(value=0.5, confidence=0.50, source=src)
    parent_rev.expand("compute_wallet", "cost_per_query", pv_prior)

    branch_id = WorldModelCoordinator.create_branch("main")

    # Optimize cost action simulation
    action = {"type": "optimize_cost"}
    WorldModelCoordinator.simulate_action(branch_id, action)

    # Execute merge back to main world
    # This should trigger Bayesian update instead of direct overwrite
    success = WorldModelCoordinator.merge_branch(branch_id)
    assert success is True

    # Verify that the value was updated in main world
    main_wallet = WorldModelCoordinator.get_entity("economic", "compute_wallet", "main")
    
    # Bayesian likelihood updates should update the property value in Main World
    assert main_wallet.properties["cost_per_query"] == 0.01
    
    # Check parent revision state is updated
    updated_pv = parent_rev.belief_engine.state.get_property("compute_wallet", "cost_per_query")
    assert updated_pv.value == 0.01
