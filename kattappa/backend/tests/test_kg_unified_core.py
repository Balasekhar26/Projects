import pytest
import time
import os
import shutil
from typing import Any

from backend.core.knowledge_graph import KnowledgeGraph, EntityType, RelationType
from backend.core.cos.entity_system import Relation, AliasRegistry, EntityMergeManager, PhysicalEntity
from backend.core.cos.belief_engine import BeliefEngine
from backend.core.cos.state_representation import BeliefState, ObservedState, PropertyValue, EvidenceSource
from backend.core.cos.unified_retrieval import UnifiedRetrievalPipeline
from backend.core.config import load_config


@pytest.fixture(autouse=True)
def clean_kg_db(tmp_path):
    """Ensures each test gets a clean, separate temporary database."""
    temp_dir = str(tmp_path / "kg_test_data")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Instantiate clean database
    kg_instance = KnowledgeGraph(temp_dir)
    # Monkeypatch singleton
    orig_instance = KnowledgeGraph._instance
    KnowledgeGraph._instance = kg_instance
    AliasRegistry.reset()
    
    yield kg_instance
    
    # Restore singleton
    KnowledgeGraph._instance = orig_instance
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_persistent_pkg_dijkstra_and_query():
    kg = KnowledgeGraph.get_instance()
    
    # Create nodes: A, B, C
    kg.add_node(name="NodeA", entity_type=EntityType.CONCEPT, node_id="node_A", confidence=0.9)
    kg.add_node(name="NodeB", entity_type=EntityType.CONCEPT, node_id="node_B", confidence=0.8)
    kg.add_node(name="NodeC", entity_type=EntityType.CONCEPT, node_id="node_C", confidence=0.95)
    
    # Add relations
    kg.add_edge(source_id="node_A", target_id="node_B", relation_type="RELATED_TO", confidence=0.9)
    kg.add_edge(source_id="node_B", target_id="node_C", relation_type="RELATED_TO", confidence=0.8)
    
    # Test Dijkstra path
    top_paths = kg.find_top_k_paths("node_A", "node_C", k=1)
    assert len(top_paths) == 1
    assert top_paths[0][0] == ["node_A", "node_B", "node_C"]
    
    # Test joint path probability with node discounting:
    # A->B->C = (0.9 * 0.8 * 0.95) * (0.9 * 0.8) = 0.684 * 0.72 = 0.49248
    res = kg.query_probabilistic("node_A", "node_C")
    assert pytest.approx(res.combined_probability, 0.0001) == 0.49248


def test_belief_engine_and_tms_persistence():
    kg = KnowledgeGraph.get_instance()
    
    # Create dependent nodes
    kg.add_node(name="ParentNode", entity_type=EntityType.CONCEPT, node_id="parent_node", confidence=1.0)
    kg.add_node(name="ChildNode", entity_type=EntityType.CONCEPT, node_id="child_node", confidence=0.9)
    
    # Initialize belief state and engine
    b_state = BeliefState(state_id="test_belief", branch_id="main", timestamp=time.time())
    engine = BeliefEngine(b_state)
    
    # Setup values in belief state
    src = EvidenceSource(name="sensor_A", source_type="sensor", reliability=0.9)
    pv_parent = PropertyValue(value="OK", confidence=1.0, source=src)
    pv_child = PropertyValue(value="ACTIVE", confidence=0.9, source=src)
    
    b_state.set_property("parent_node", "status", pv_parent)
    b_state.set_property("child_node", "status", pv_child)
    
    # Register dependency: Child depends on Parent
    engine.dependency_tracker.register_dependency("child_node", "status", "parent_node", "status")
    
    # Directly set parent confidence to 0.3 to trigger TMS bounding
    pv_parent_low = PropertyValue(value="OK", confidence=0.3, source=src)
    b_state.set_property("parent_node", "status", pv_parent_low)
    
    # Run propagation
    engine.dependency_tracker.propagate_change(b_state, "parent_node", "status")
    
    # Verify child is bounded by parent's low confidence in both memory state and database!
    child_pv = b_state.get_property("child_node", "status")
    assert child_pv.confidence == 0.3
    
    db_node = kg.get_node("child_node")
    assert db_node["confidence"] == 0.3
    assert db_node["belief_state"] == "HYPOTHESIS"


def test_alias_resolution_and_synonym_mergers():
    kg = KnowledgeGraph.get_instance()
    
    # Create two nodes to merge
    kg.add_node(name="Entity1", entity_type=EntityType.CONCEPT, node_id="ent_1", properties={"role": "admin"}, confidence=0.8)
    kg.add_node(name="Entity2", entity_type=EntityType.CONCEPT, node_id="ent_2", properties={"region": "US"}, confidence=0.9)
    
    kg.add_edge(source_id="ent_1", target_id="target_node", relation_type="USES", confidence=0.9)
    kg.add_edge(source_id="source_node", target_id="ent_2", relation_type="DEPENDS_ON", confidence=0.8)
    
    # Register initial aliases so database has references
    AliasRegistry.register_alias("canonical.ent.1", "ent_1")
    AliasRegistry.register_alias("canonical.ent.2", "ent_2")

    # Reconcile / Merge
    # EntityMergeManager also triggers db merge
    p_ent = PhysicalEntity(entity_id="ent_1", canonical_id="canonical.ent.1", entity_type="physical")
    s_ent = PhysicalEntity(entity_id="ent_2", canonical_id="canonical.ent.2", entity_type="physical")
    EntityMergeManager.merge_entities(p_ent, s_ent)
    
    # Verify DB node 2 is deleted, node 1 has consolidated properties and aliases
    assert kg.get_node("ent_2") is None
    
    ent_1_node = kg.get_node("ent_1")
    assert ent_1_node is not None
    assert ent_1_node["properties"]["region"] == "US"
    assert ent_1_node["confidence"] == 0.9  # Max of 0.8 and 0.9
    
    # Verify alias resolution
    resolved = AliasRegistry.resolve("canonical.ent.2")
    assert resolved == "ent_1"


def test_unified_retrieval_pipeline_execution():
    kg = KnowledgeGraph.get_instance()
    
    # Add dummy entity and path
    kg.add_node(name="Python", entity_type=EntityType.CONCEPT, node_id="python_id", confidence=0.9)
    kg.add_node(name="Compiler", entity_type=EntityType.CONCEPT, node_id="compiler_id", confidence=0.85)
    kg.add_edge(source_id="python_id", target_id="compiler_id", relation_type="USES", confidence=0.9)
    
    # Run unified retrieval
    result = UnifiedRetrievalPipeline.retrieve(query="Python compiler query", min_probability=0.01)
    assert "facts" in result
    assert "episodes" in result
    assert "graph_paths" in result
    assert "provenance" in result
    assert "context_text" in result
