import pytest
import os
import tempfile
import time
from backend.core.memory.memory_store import MemoryStore
from backend.core.memory.memory_scorer import MemoryScorer
from backend.core.memory.memory_retriever import MemoryRetriever
from backend.core.memory.memory_manager import MemoryManager

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    # Set up isolated workspace environment
    temp_dir = tempfile.mkdtemp(prefix="kattappa_memory_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    # Clean databases
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_memory_store_operations() -> None:
    # 1. Test upsert entity
    MemoryStore.upsert_entity("entity_bala", "Bala", "Person", {"role": "developer"})
    entities = MemoryStore.get_all_entities()
    assert len(entities) == 1
    assert entities[0]["name"] == "Bala"
    assert entities[0]["type"] == "Person"

    # 2. Test relationship link
    MemoryStore.upsert_entity("entity_kattappa", "Kattappa", "Project")
    MemoryStore.add_relationship("rel_1", "entity_bala", "entity_kattappa", "develops")
    rels = MemoryStore.get_all_relationships()
    assert len(rels) == 1
    assert rels[0]["predicate"] == "develops"

    # 3. Test memory insert
    MemoryStore.add_memory("mem_1", "Bala works on Kattappa", "semantic", 0.9, 1.0)
    mems = MemoryStore.get_all_memories()
    assert len(mems) == 1
    assert mems[0]["content"] == "Bala works on Kattappa"

def test_memory_scorer() -> None:
    # 1. Base score calculation
    mem = {
        "importance": 0.8,
        "confidence": 1.0,
        "access_count": 0,
        "created_at": None
    }
    score1 = MemoryScorer.calculate_score(mem)
    assert abs(score1 - 0.8) < 1e-5

    # 2. Access count logarithmic boost
    mem["access_count"] = 5
    score2 = MemoryScorer.calculate_score(mem)
    assert score2 > score1

def test_memory_manager_and_retrieval() -> None:
    # 1. Record interaction text containing Bala and Kattappa keywords
    MemoryManager.record_interaction("Bala is building Kattappa in Telugu on Windows", importance=0.9)
    
    entities = MemoryStore.get_all_entities()
    names = {e["name"] for e in entities}
    assert "Bala" in names
    assert "Kattappa" in names
    assert "Telugu" in names
    assert "Windows" in names
    
    rels = MemoryStore.get_all_relationships()
    assert len(rels) > 0
    
    # 2. Retrieve context targeting "Bala"
    context = MemoryManager.get_planner_context("Bala")
    assert len(context["relevant_memories"]) > 0
    assert any("develops" in r or "prefers" in r or "uses" in r for r in context["relationships"])
