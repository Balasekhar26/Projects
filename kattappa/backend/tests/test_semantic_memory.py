import pytest
import tempfile
from backend.core.memory.memory_store import MemoryStore
from backend.core.semantic_memory_engine.semantic_store import SemanticStore
from backend.core.semantic_memory_engine.concept_ontology import ConceptOntology
from backend.core.semantic_memory_engine.knowledge_abstraction import KnowledgeAbstraction
from backend.core.semantic_memory_engine.semantic_memory_engine import SemanticMemoryEngine

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_semantic_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_semantic_facts_storage() -> None:
    store = SemanticStore()
    store.save_fact("python", "is_a", "programming_language", 0.95)
    
    fact = store.get_fact("python", "is_a", "programming_language")
    assert fact is not None
    assert fact["confidence"] == 0.95

def test_concept_ontology_traversal() -> None:
    ontology = ConceptOntology()
    ancestors = ontology.get_ancestors("python")
    
    assert len(ancestors) == 2
    assert ancestors[0] == "programming_language"
    assert ancestors[1] == "software_tool"

def test_confidence_consolidation() -> None:
    val = KnowledgeAbstraction.consolidate_confidence(1.0, 0.5)
    assert pytest.approx(val) == 0.85

def test_memory_engine_workflow(test_db_setup) -> None:
    engine = SemanticMemoryEngine()
    
    # 1. Store first fact
    engine.record_fact("vscode", "is_a", "text_editor", 1.0)
    assert engine.get_fact_confidence("vscode", "is_a", "text_editor") == 1.0
    
    # 2. Consolidate fact confidence
    engine.record_fact("vscode", "is_a", "text_editor", 0.5)
    assert pytest.approx(engine.get_fact_confidence("vscode", "is_a", "text_editor")) == 0.85
    
    # 3. Taxonomy chain resolution
    chain = engine.get_relationship_chain("vscode")
    assert chain == ["text_editor", "software_tool"]
