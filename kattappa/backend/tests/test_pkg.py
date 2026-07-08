"""Tests for Phase K21.7: Probabilistic Knowledge Graph (PKG)."""
from __future__ import annotations

import time
import pytest
from backend.core.cos.entity_system import Relation
from backend.core.cos.pkg import ProbabilisticKnowledgeGraph


def test_path_probability_propagation():
    pkg = ProbabilisticKnowledgeGraph()

    # Path: A -> B -> C
    # A -> B (conf = 0.9)
    # B -> C (conf = 0.8)
    rel_ab = Relation(source_uuid="entity_A", target_uuid="entity_B", relation_type="knows", confidence=0.9, valid_from=100.0)
    rel_bc = Relation(source_uuid="entity_B", target_uuid="entity_C", relation_type="knows", confidence=0.8, valid_from=100.0)

    pkg.add_relation(rel_ab)
    pkg.add_relation(rel_bc)

    paths = pkg.find_paths("entity_A", "entity_C")
    assert len(paths) == 1
    
    path_nodes, path_prob = paths[0]
    assert path_nodes == ["entity_A", "entity_B", "entity_C"]
    assert pytest.approx(path_prob, 0.001) == 0.72  # 0.9 * 0.8


def test_noisy_or_parallel_paths():
    pkg = ProbabilisticKnowledgeGraph()

    # Redundant Paths from A -> C:
    # Path 1: A -> B -> C (prob = 0.9 * 0.8 = 0.72)
    # Path 2: A -> D -> C (prob = 0.7 * 0.6 = 0.42)
    rel_ab = Relation(source_uuid="entity_A", target_uuid="entity_B", relation_type="knows", confidence=0.9, valid_from=100.0)
    rel_bc = Relation(source_uuid="entity_B", target_uuid="entity_C", relation_type="knows", confidence=0.8, valid_from=100.0)
    rel_ad = Relation(source_uuid="entity_A", target_uuid="entity_D", relation_type="knows", confidence=0.7, valid_from=100.0)
    rel_dc = Relation(source_uuid="entity_D", target_uuid="entity_C", relation_type="knows", confidence=0.6, valid_from=100.0)

    pkg.add_relation(rel_ab)
    pkg.add_relation(rel_bc)
    pkg.add_relation(rel_ad)
    pkg.add_relation(rel_dc)

    # Inferred probability using Noisy-OR: 1 - (1 - 0.72)*(1 - 0.42) = 1 - 0.28 * 0.58 = 1 - 0.1624 = 0.8376
    inferred_prob = pkg.infer_indirect_relation_probability("entity_A", "entity_C")
    assert pytest.approx(inferred_prob, 0.0001) == 0.8376


def test_non_existent_path():
    pkg = ProbabilisticKnowledgeGraph()
    rel_ab = Relation(source_uuid="entity_A", target_uuid="entity_B", relation_type="knows", confidence=0.9, valid_from=100.0)
    pkg.add_relation(rel_ab)

    assert pkg.infer_indirect_relation_probability("entity_A", "entity_C") == 0.0
