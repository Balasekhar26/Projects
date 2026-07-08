"""Tests for Phase K21.7.4 - K21.7.6: PKG & Belief Engine Integration."""
from __future__ import annotations

import pytest
from backend.core.cos.entity_system import Relation, PhysicalEntity
from backend.core.cos.pkg import ProbabilisticKnowledgeGraph
from backend.core.cos.coordinator import WorldModelCoordinator


def test_probabilistic_nodes_discount():
    pkg = ProbabilisticKnowledgeGraph()

    # Path: A -> B -> C
    # A -> B (conf = 0.9)
    # B -> C (conf = 0.8)
    rel_ab = Relation(source_uuid="node_A", target_uuid="node_B", relation_type="link", confidence=0.9, valid_from=0.0)
    rel_bc = Relation(source_uuid="node_B", target_uuid="node_C", relation_type="link", confidence=0.8, valid_from=0.0)
    pkg.add_relation(rel_ab)
    pkg.add_relation(rel_bc)

    # Register node confidences
    pkg.register_node_confidence("node_A", 0.9)
    pkg.register_node_confidence("node_B", 0.8)
    pkg.register_node_confidence("node_C", 0.9)

    res = pkg.query("node_A", "node_C")
    
    # Path probability = (0.9 * 0.8 * 0.9) * (0.9 * 0.8) = 0.648 * 0.72 = 0.46656
    assert pytest.approx(res.combined_probability, 0.0001) == 0.46656


def test_best_first_dijkstra_search():
    pkg = ProbabilisticKnowledgeGraph()

    # Path 1: A -> B (0.9) -> C (0.9) -> Path prob = 0.81
    # Path 2: A -> D (0.9) -> C (0.5) -> Path prob = 0.45
    rel_ab = Relation(source_uuid="node_A", target_uuid="node_B", relation_type="link", confidence=0.9, valid_from=0.0)
    rel_bc = Relation(source_uuid="node_B", target_uuid="node_C", relation_type="link", confidence=0.9, valid_from=0.0)
    
    rel_ad = Relation(source_uuid="node_A", target_uuid="node_D", relation_type="link", confidence=0.9, valid_from=0.0)
    rel_dc = Relation(source_uuid="node_D", target_uuid="node_C", relation_type="link", confidence=0.5, valid_from=0.0)

    pkg.add_relation(rel_ab)
    pkg.add_relation(rel_bc)
    pkg.add_relation(rel_ad)
    pkg.add_relation(rel_dc)

    # Find top paths
    top_paths = pkg.find_top_k_paths("node_A", "node_C", k=2)
    assert len(top_paths) == 2
    
    # Best path should be A -> B -> C
    assert top_paths[0][0] == ["node_A", "node_B", "node_C"]
    assert pytest.approx(top_paths[0][2], 0.001) == 0.81


def test_ontological_transitivity():
    pkg = ProbabilisticKnowledgeGraph()

    # A --[INSTANCE_OF]--> B
    # B --[SUBCLASS_OF]--> C
    rel_inst = Relation(source_uuid="entity_A", target_uuid="entity_B", relation_type="INSTANCE_OF", confidence=0.9, valid_from=0.0)
    rel_sub = Relation(source_uuid="entity_B", target_uuid="entity_C", relation_type="SUBCLASS_OF", confidence=0.9, valid_from=0.0)
    
    pkg.add_relation(rel_inst)
    pkg.add_relation(rel_sub)

    # Search with allowed relations set to INSTANCE_OF.
    # The chain INSTANCE_OF + SUBCLASS_OF semantically composes to INSTANCE_OF.
    res = pkg.query("entity_A", "entity_C", allowed_relations=["INSTANCE_OF"])
    assert len(res.paths) == 1
    assert res.paths[0] == ["entity_A", "entity_B", "entity_C"]


def test_belief_engine_coordinator_sync():
    WorldModelCoordinator.reset()

    # Create entity containing a relation
    rel = Relation(source_uuid="entity_A", target_uuid="entity_B", relation_type="friend", confidence=0.95, valid_from=0.0)
    entity = PhysicalEntity(
        entity_id="entity_A",
        canonical_id="physical.entity.A",
        entity_type="physical",
        relations=[rel]
    )
    entity.confidence = 0.85

    # Register entity on Main World
    WorldModelCoordinator.register_entity("physical", entity)

    # Retrieve PKG and verify node confidence and relations synced automatically
    pkg = WorldModelCoordinator._pkgs["main"]
    assert pkg.get_node_confidence("entity_A") == 0.85
    
    rels = pkg.get_relations("entity_A")
    assert len(rels) == 1
    assert rels[0].target_uuid == "entity_B"
    assert rels[0].confidence == 0.95
