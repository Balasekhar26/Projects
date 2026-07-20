import pytest
import os
import tempfile
from backend.core.memory.memory_store import MemoryStore
from backend.core.rag.rag_engine import RAGEngine
from backend.core.graphrag.graph_extractor import GraphExtractor
from backend.core.graphrag.graph_retriever import GraphRetriever
from backend.core.planner.context_builder import ContextBuilder

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_graphrag_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_heuristic_relationships_extraction() -> None:
    text = "ESP32 controls motor driver. low voltage causes reboot."
    rels = GraphExtractor.extract_relations(text, "chk_1")
    
    assert len(rels) == 2
    assert rels[0]["source_id"] == "esp32"
    assert rels[0]["target_id"] == "motor_driver"
    assert rels[0]["predicate"] == "controls"
    
    assert rels[1]["source_id"] == "low_voltage"
    assert rels[1]["target_id"] == "reboot"
    assert rels[1]["predicate"] == "causes"

def test_graphrag_traversals_and_cyclic_paths(test_db_setup) -> None:
    # Set up entity relationship chain: A -> B -> C -> A (cyclic)
    MemoryStore.upsert_entity("ent_a", "Node A", "concept")
    MemoryStore.upsert_entity("ent_b", "Node B", "concept")
    MemoryStore.upsert_entity("ent_c", "Node C", "concept")
    
    MemoryStore.add_graph_relationship("r1", "ent_a", "ent_b", "depends_on", {}, "chk_1", "regex")
    MemoryStore.add_graph_relationship("r2", "ent_b", "ent_c", "depends_on", {}, "chk_1", "regex")
    MemoryStore.add_graph_relationship("r3", "ent_c", "ent_a", "depends_on", {}, "chk_1", "regex")
    
    rels = GraphRetriever.traverse_relationships("ent_a", max_depth=3)
    # Check that all relationships are resolved and cyclic paths did not cause infinite loop
    assert len(rels) == 3
    rel_ids = [r["id"] for r in rels]
    assert "r1" in rel_ids
    assert "r2" in rel_ids
    assert "r3" in rel_ids

def test_document_graph_ingestion_and_query(test_db_setup) -> None:
    doc_path = os.path.join(test_db_setup, "hardware_spec.txt")
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write("STM32 controls motor driver. motor driver manages actuator.")
        
    RAGEngine.index_document("doc_hw", "Hardware Specifications", "local", doc_path)
    
    # Query graph retrieval
    context = GraphRetriever.query_graph("STM32 motor actuator details")
    
    assert "STM32" in context
    assert "motor driver" in context
    assert "actuator" in context
    assert "controls" in context
    
    # Check mentions logging
    mentions = MemoryStore.get_entity_mentions("stm32")
    assert len(mentions) >= 1

def test_planner_context_graphrag_integration(test_db_setup) -> None:
    doc_path = os.path.join(test_db_setup, "spec.txt")
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write("OpenCV requires numpy. numpy provides arrays.")
        
    RAGEngine.index_document("doc_spec", "Spec Sheet", "local", doc_path)
    
    planner_context = ContextBuilder.build_context("build OpenCV python arrays")
    assert "graph_context" in planner_context
    assert "OpenCV" in planner_context["graph_context"]
    assert "numpy" in planner_context["graph_context"]
