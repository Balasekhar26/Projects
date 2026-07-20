import pytest
import os
import tempfile
from backend.core.memory.memory_store import MemoryStore
from backend.core.rag.chunker import Chunker
from backend.core.rag.rag_engine import RAGEngine
from backend.core.planner.context_builder import ContextBuilder

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_rag_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_chunker_segmentation() -> None:
    text = " ".join([f"word{i}" for i in range(100)])
    # word_chunk_size = 512 * 0.75 = 384 words.
    # If we request a very small chunk limit for testing:
    chunks = Chunker.chunk_text(text, chunk_size=40, overlap=10)
    assert len(chunks) > 1
    assert chunks[0]["chunk_index"] == 0
    assert "word0" in chunks[0]["text"]
    assert chunks[0]["token_count"] > 0

def test_document_indexing_and_database_sync(test_db_setup) -> None:
    # 1. Create temporary doc file
    temp_path = os.path.join(test_db_setup, "warranty_info.txt")
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write("Zen Technologies provides a 24 month warranty for simulator products. Warranty excludes accidental damage.")
        
    RAGEngine.index_document(
        doc_id="doc_warranty",
        title="Zen Technologies Simulator Warranty Policies",
        source="local_file",
        file_path=temp_path
    )
    
    # 2. Assert records inside SQLite
    docs = MemoryStore.get_all_documents()
    assert len(docs) == 1
    assert docs[0]["doc_id"] == "doc_warranty"
    assert docs[0]["title"] == "Zen Technologies Simulator Warranty Policies"
    
    chunks = MemoryStore.get_document_chunks("doc_warranty")
    assert len(chunks) >= 1
    assert "warranty" in chunks[0]["text"]

def test_hybrid_search_and_fusion_ranking(test_db_setup) -> None:
    # 1. Ingest warranty document
    doc1_path = os.path.join(test_db_setup, "doc1.txt")
    with open(doc1_path, "w", encoding="utf-8") as f:
        f.write("Zen Technologies provides simulator warranty coverage. Claims require invoices.")
    RAGEngine.index_document("d1", "Zen Warranty", "local", doc1_path)
    
    # 2. Ingest unrelated planetary document
    doc2_path = os.path.join(test_db_setup, "doc2.txt")
    with open(doc2_path, "w", encoding="utf-8") as f:
        f.write("Planetary systems orbit stars in elliptical path loops. Gravity keeps them bound.")
    RAGEngine.index_document("d2", "Space Orbits", "local", doc2_path)
    
    # 3. Query RAG engine for warranty
    context = RAGEngine.query("Zen simulator warranty claims", top_k=1)
    
    assert "Zen Warranty" in context
    assert "invoices" in context
    # Planetary context should NOT be retrieved since it's unrelated
    assert "Planetary systems" not in context
    
    # Check stats logged
    conn = MemoryStore._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM retrieval_stats")
    stats = cursor.fetchall()
    assert len(stats) >= 1
    assert stats[0]["retrieval_count"] == 1
    assert stats[0]["success_count"] == 1

def test_planner_context_hybrid_retrieval(test_db_setup) -> None:
    doc1_path = os.path.join(test_db_setup, "doc1.txt")
    with open(doc1_path, "w", encoding="utf-8") as f:
        f.write("FastAPI is a modern web framework for building APIs with Python.")
    RAGEngine.index_document("d_api", "FastAPI Reference", "local", doc1_path)
    
    planner_context = ContextBuilder.build_context("build FastAPI python endpoints")
    assert "rag_context" in planner_context
    assert "FastAPI Reference" in planner_context["rag_context"]
