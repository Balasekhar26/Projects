import pytest
import os
import tempfile
from backend.core.memory.memory_store import MemoryStore
from backend.core.rag.rag_engine import RAGEngine
from backend.core.rag.adaptive_feedback import AdaptiveFeedback

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_adaptive_rag_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_adaptive_feedback_storage() -> None:
    AdaptiveFeedback.record_feedback(
        query="test queries",
        retrieved_chunk_ids=["chk_a", "chk_b"],
        selected_chunk_ids=["chk_a"],
        answer_quality=0.1,
        user_feedback=-1
    )
    
    feedbacks = MemoryStore.get_all_retrieval_feedback()
    assert len(feedbacks) == 1
    assert feedbacks[0]["query"] == "test queries"
    assert feedbacks[0]["user_feedback"] == -1
    
    penalties = AdaptiveFeedback.get_chunk_penalties()
    # chk_b was not selected, so it should be penalized
    assert "chk_b" in penalties
    assert penalties["chk_b"] > 0
    # chk_a was selected, so it should have 0 penalty
    assert "chk_a" not in penalties

def test_ranking_shift_on_negative_feedback(test_db_setup) -> None:
    # 1. Index doc 1 and doc 2
    d1_path = os.path.join(test_db_setup, "d1.txt")
    with open(d1_path, "w", encoding="utf-8") as f:
        f.write("Zen simulator warranty details cover hardware failures.")
    RAGEngine.index_document("d1", "Zen Warranty", "local", d1_path)
    
    d2_path = os.path.join(test_db_setup, "d2.txt")
    with open(d2_path, "w", encoding="utf-8") as f:
        f.write("Planetary orbits revolve around stars in elliptical patterns.")
    RAGEngine.index_document("d2", "Orbits", "local", d2_path)
    
    # 2. Assert standard query ranks warranty doc first
    context_initial = RAGEngine.query("Zen simulator warranty details", top_k=1)
    assert "Zen Warranty" in context_initial
    assert "Orbits" not in context_initial

    # 3. Simulate negative feedback for the warranty chunk (user ignored it, selected the orbits chunk instead)
    # Retrieved: ["chk_d1_0", "chk_d2_0"], Selected: ["chk_d2_0"]
    AdaptiveFeedback.record_feedback(
        query="Zen simulator warranty details",
        retrieved_chunk_ids=["chk_d1_0", "chk_d2_0"],
        selected_chunk_ids=["chk_d2_0"],
        answer_quality=0.0,
        user_feedback=-1
    )
    
    # 4. Query again - the penalty on d1 should shift the ranking so d2 (unrelated orbits) ranks higher!
    context_penalized = RAGEngine.query("Zen simulator warranty details", top_k=1)
    assert "Orbits" in context_penalized
    assert "Zen Warranty" not in context_penalized

def test_graphrag_early_layout_schema() -> None:
    # Pre-populate parent tables to satisfy foreign key requirements
    MemoryStore.upsert_entity("ent_fastapi", "FastAPI", "framework")
    MemoryStore.add_document("doc1", "FastAPI Reference", "local")
    MemoryStore.add_chunk("chk_d1_0", "doc1", 0, "FastAPI is a Python web framework.", "emb1", 5)

    # Verify entity mention additions
    MemoryStore.add_entity_mention(
        mention_id="m1",
        entity_id="ent_fastapi",
        chunk_id="chk_d1_0",
        sentence_context="FastAPI is a Python web framework."
    )
    
    mentions = MemoryStore.get_entity_mentions("ent_fastapi")
    assert len(mentions) == 1
    assert mentions[0]["mention_id"] == "m1"
    assert mentions[0]["chunk_id"] == "chk_d1_0"
    
    # Verify entity embedding updates
    MemoryStore.update_entity_embedding("ent_fastapi", [0.12, 0.34, 0.56])
    
    conn = MemoryStore._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM entity_embeddings WHERE entity_id = 'ent_fastapi'")
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert "0.12" in rows[0]["embedding_json"]
