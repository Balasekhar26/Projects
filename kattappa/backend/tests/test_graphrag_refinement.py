import pytest
import os
import tempfile
from backend.core.memory.memory_store import MemoryStore
from backend.core.graphrag.graph_engine import GraphEngine
from backend.core.graphrag.graph_retriever import GraphRetriever

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_graph_ref_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_dynamic_depth_and_confidence_decay(test_db_setup) -> None:
    # 1. Store entities
    MemoryStore.upsert_entity("ent_a", "Node A", "concept")
    MemoryStore.upsert_entity("ent_b", "Node B", "concept")
    MemoryStore.upsert_entity("ent_c", "Node C", "concept")
    
    # 2. Store relationships with specified confidences
    # A -> B (confidence 0.90)
    MemoryStore.add_graph_relationship(
        rel_id="r1",
        source_id="ent_a",
        target_id="ent_b",
        predicate="depends_on",
        metadata={"confidence": 0.90, "category": "Dependency"},
        source_chunk_id="chk_1",
        extraction_method="regex_rule"
    )
    # B -> C (confidence 0.80)
    MemoryStore.add_graph_relationship(
        rel_id="r2",
        source_id="ent_b",
        target_id="ent_c",
        predicate="controls",
        metadata={"confidence": 0.80, "category": "Control"},
        source_chunk_id="chk_2",
        extraction_method="regex_rule"
    )
    
    # 3. Retrieve traversals for Node A
    # Depth 1 only returns r1 (1 relation).
    # Since 1 is less than the threshold (2), the retriever should dynamically expand to depth 2 and return both r1 and r2!
    context = GraphRetriever.query_graph("Node A query", max_depth=3)
    
    assert "Node A" in context
    assert "Node B" in context
    assert "Node C" in context
    
    # Check time-decayed confidence:
    # r1 confidence = 0.90
    assert "confidence: 0.90" in context
    # r2 confidence = 0.90 * 0.80 = 0.72
    assert "confidence: 0.72" in context
