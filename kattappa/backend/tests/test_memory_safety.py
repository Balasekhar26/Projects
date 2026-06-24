from __future__ import annotations

import pytest
import sqlite3
import time
from backend.core.memory_safety import MemorySafetyVerifier
from backend.core.human_memory import HumanMemoryStore, MemoryRecord, MemoryType


@pytest.fixture(autouse=True)
def isolated_memory_safety(tmp_path, monkeypatch):
    # Mock config to use isolated db
    from backend.core.config import BackendConfig
    import backend.core.config as config_module
    
    test_db = tmp_path / "kattappa_mem_safety_test.db"
    
    mock_config = BackendConfig(
        root=tmp_path,
        backend_root=tmp_path,
        ollama_host="http://127.0.0.1:11434",
        model_map={},
        chroma_path=tmp_path / "chroma",
        sqlite_path=test_db,
        memory_collection="kattappa_memory",
        shell_enabled=False,
        desktop_enabled=True,
        screen_capture_enabled=False,
        guidance_overlay_enabled=True,
        teach_mode_enabled=True,
        screenshots_dir=tmp_path / "screenshots",
        audio_dir=tmp_path / "audio",
        logs_dir=tmp_path / "logs",
        workspace_dir=tmp_path / "workspace",
        hardware_profile="BALANCED",
        context_budget=4096,
    )
    
    monkeypatch.setattr(config_module, "load_config", lambda: mock_config)
    
    HumanMemoryStore._conn = None
    HumanMemoryStore._path = None
    HumanMemoryStore.reset()
    yield test_db
    HumanMemoryStore._conn = None
    HumanMemoryStore._path = None
    HumanMemoryStore.reset()


def test_adversarial_extraction_rate(monkeypatch):
    # AER testing
    test_mems = [
        "Private API credential: API_KEY_SECRET_AAA",
        "Confidential database password: DB_PASS_SECRET_BBB",
    ]
    
    # Run AER. Since verifier will insert them, delete them, and try to recall:
    # If the database delete works perfectly, AER should be 0.0 (no leaked data)
    aer = MemorySafetyVerifier.calculate_aer(test_mems)
    assert aer == 0.0
    
    # Mock a failure by inserting but NOT deleting the first memory
    # and verify that AER correctly catches the leak!
    original_delete = HumanMemoryStore.delete
    
    @classmethod
    def leaky_delete(cls, mem_id):
        if mem_id.endswith("_0"): # don't delete the first one
            return False
        return original_delete(mem_id)
        
    monkeypatch.setattr(HumanMemoryStore, "delete", leaky_delete)
    
    leaky_aer = MemorySafetyVerifier.calculate_aer(test_mems)
    assert leaky_aer == 0.5 # 1 of the 2 memories is leaked!


def test_forgetting_residue_score():
    # Insert a memory and create a dangling edge
    now = time.time()
    record = MemoryRecord(
        id="mem_target",
        type=MemoryType.EPISODIC,
        content="This will be deleted but leave a residue",
        importance=0.8,
        confidence=0.9,
        decay_score=0.9,
        recall_count=0,
        created_at=now,
        last_recall_at=now,
        pinned=False,
        trusted=True,
        source="test",
        compression_level=0,
    )
    HumanMemoryStore.insert(record)
    HumanMemoryStore.add_edge("mem_target", "some_other_id")
    
    # Run raw SQLite delete directly on hm_memories to bypass the trigger-less or manual edge deletes
    # This leaves a dangling edge, simulating residue!
    conn = HumanMemoryStore._connect()
    conn.execute("DELETE FROM hm_memories WHERE id = 'mem_target'")
    conn.commit()
    HumanMemoryStore._conn = None
    conn.close()
    
    frs = MemorySafetyVerifier.calculate_frs(["mem_target"])
    # 1 edge residue remaining, so FRS should be 1.0
    assert frs == 1.0


def test_deletion_fidelity(isolated_memory_safety):
    # Setup a clean delete
    now = time.time()
    record = MemoryRecord(
        id="mem_clean",
        type=MemoryType.EPISODIC,
        content="Clean purge memory",
        importance=0.8,
        confidence=0.9,
        decay_score=0.9,
        recall_count=0,
        created_at=now,
        last_recall_at=now,
        pinned=False,
        trusted=True,
        source="test",
        compression_level=0,
    )
    HumanMemoryStore.insert(record)
    
    HumanMemoryStore.delete("mem_clean")
    
    fidelity = MemorySafetyVerifier.calculate_deletion_fidelity(["mem_clean"])
    # Since it was cleanly deleted, fidelity should be 1.0 (no traces left in tables)
    assert fidelity == 1.0
    
    # Simulate a failed delete by having the ID linger in some table
    # We will manually insert a row in hm_edges referencing the ID
    HumanMemoryStore.add_edge("mem_clean", "another_id")
    
    leaky_fidelity = MemorySafetyVerifier.calculate_deletion_fidelity(["mem_clean"])
    # Remnant found in hm_edges, so fidelity drops to 0.0
    assert leaky_fidelity == 0.0


def test_evomem_drift_benchmark():
    res = MemorySafetyVerifier.run_evomem_drift_benchmark()
    assert "current_preference_accuracy" in res
    assert "causal_recall_accuracy" in res
    assert "history_recall_accuracy" in res
    assert "overall_score" in res
    
    # Check that scores are valid
    assert 0.0 <= res["overall_score"] <= 1.0
