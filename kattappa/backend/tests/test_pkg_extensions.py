"""Tests for Phase K21.7.1 - K21.7.3: PKG Extensions."""
from __future__ import annotations

import time
import pytest
from backend.core.cos.entity_system import Relation
from backend.core.cos.pkg import ProbabilisticKnowledgeGraph


def test_temporal_validity_filtering():
    pkg = ProbabilisticKnowledgeGraph()

    # Relation A -> B is valid only from t=10 to t=20
    rel = Relation(
        source_uuid="entity_A",
        target_uuid="entity_B",
        relation_type="knows",
        confidence=0.9,
        valid_from=10.0,
        valid_until=20.0
    )
    pkg.add_relation(rel)

    # Query at t=15 (valid window) -> should find path
    res_valid = pkg.query("entity_A", "entity_B", at_time=15.0)
    assert len(res_valid.paths) == 1

    # Query at t=25 (expired window) -> should skip relation
    res_expired = pkg.query("entity_A", "entity_B", at_time=25.0)
    assert len(res_expired.paths) == 0


def test_relation_type_filtering():
    pkg = ProbabilisticKnowledgeGraph()

    # Path 1: A --[friend]--> B (conf = 0.9)
    # Path 2: A --[colleague]--> B (conf = 0.8)
    rel_friend = Relation(source_uuid="entity_A", target_uuid="entity_B", relation_type="friend", confidence=0.9, valid_from=0.0)
    rel_colleague = Relation(source_uuid="entity_A", target_uuid="entity_B", relation_type="colleague", confidence=0.8, valid_from=0.0)

    pkg.add_relation(rel_friend)
    pkg.add_relation(rel_colleague)

    # Only allow "friend" type
    res = pkg.query("entity_A", "entity_B", allowed_relations=["friend"])
    assert len(res.paths) == 1
    assert res.combined_probability == 0.9


def test_exact_overlap_probability_reduction():
    pkg = ProbabilisticKnowledgeGraph()

    # Path 1: A -> B (0.9) -> C (0.8)  [Path prob = 0.72]
    # Path 2: A -> B (0.9) -> D (0.7) -> C (0.6)  [Path prob = 0.378]
    # Both paths share A -> B edge.
    # Exact joint probability:
    #   P(A -> B) * [1 - (1 - P(B -> C)) * (1 - P(B -> D)*P(D -> C))]
    #   = 0.9 * [1 - (1 - 0.8) * (1 - 0.7 * 0.6)]
    #   = 0.9 * [1 - 0.2 * 0.58] = 0.9 * [1 - 0.116] = 0.9 * 0.884 = 0.7956
    rel_ab = Relation(source_uuid="entity_A", target_uuid="entity_B", relation_type="link", confidence=0.9, valid_from=0.0)
    rel_bc = Relation(source_uuid="entity_B", target_uuid="entity_C", relation_type="link", confidence=0.8, valid_from=0.0)
    rel_bd = Relation(source_uuid="entity_B", target_uuid="entity_D", relation_type="link", confidence=0.7, valid_from=0.0)
    rel_dc = Relation(source_uuid="entity_D", target_uuid="entity_C", relation_type="link", confidence=0.6, valid_from=0.0)

    pkg.add_relation(rel_ab)
    pkg.add_relation(rel_bc)
    pkg.add_relation(rel_bd)
    pkg.add_relation(rel_dc)

    res = pkg.query("entity_A", "entity_C")
    
    # Assert exact dependent calculation is strictly less than naive Noisy-OR (0.8258)
    assert pytest.approx(res.combined_probability, 0.0001) == 0.7956


def test_explainability_traces():
    pkg = ProbabilisticKnowledgeGraph()
    rel = Relation(source_uuid="entity_A", target_uuid="entity_B", relation_type="friend", confidence=0.9, valid_from=0.0)
    pkg.add_relation(rel)

    res = pkg.query("entity_A", "entity_B")
    
    # Check trace outputs
    assert res.explanation.combined_probability == 0.9
    assert "entity_A --[friend]--> entity_B" in res.explanation.edge_confidences
    assert "Query: entity_A to entity_B" in res.explanation.explanation_text
