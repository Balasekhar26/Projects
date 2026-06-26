import os
import sys
import pytest
import time
import math

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from kattappa_runtime.memory.working_memory import WorkingMemory
from kattappa_runtime.memory.episodic_memory import EpisodicMemory
from kattappa_runtime.memory.semantic_memory import SemanticMemory
from kattappa_runtime.memory.ranker import MemoryRanker
from kattappa_runtime.memory.retriever import MemoryRetriever
from kattappa_runtime.memory.writer import MemoryWriter
from kattappa_runtime.memory.consolidator import MemoryConsolidator

def test_working_memory():
    wm = WorkingMemory()
    assert wm.get("active_project") == "Kattappa"
    
    wm.set("active_project", "Balu")
    assert wm.get("active_project") == "Balu"
    
    wm.add_task("test task")
    assert "test task" in wm.get("open_tasks")
    
    wm.reset()
    assert wm.get("active_project") is None
    assert wm.get("open_tasks") == []

def test_episodic_memory():
    test_file = "/tmp/test_episodic.jsonl"
    if os.path.exists(test_file):
        os.remove(test_file)
        
    ep = EpisodicMemory(filepath=test_file)
    ep.add_episode("User ran compiler script", importance=0.9, confidence=1.0)
    
    # Reload and assert
    ep2 = EpisodicMemory(filepath=test_file)
    events = ep2.get_all()
    assert len(events) == 1
    assert events[0]["event"] == "User ran compiler script"
    assert events[0]["importance"] == 0.9
    
    if os.path.exists(test_file):
        os.remove(test_file)

def test_semantic_memory():
    test_file = "/tmp/test_semantic.jsonl"
    if os.path.exists(test_file):
        os.remove(test_file)
        
    sm = SemanticMemory(filepath=test_file)
    sm.store_fact(subject="Balu", relation="role", fact="Architect", confidence=0.99)
    
    # Check deduplication update instead of duplicate
    sm.store_fact(subject="Balu", relation="role", fact="Lead Architect", confidence=1.0)
    
    sm2 = SemanticMemory(filepath=test_file)
    facts = sm2.get_all()
    assert len(facts) == 1
    assert facts[0]["fact"] == "Lead Architect"
    assert facts[0]["confidence"] == 1.0
    
    # Test removal
    sm2.remove_fact(subject="Balu", relation="role")
    assert len(sm2.get_all()) == 0
    
    if os.path.exists(test_file):
        os.remove(test_file)

def test_memory_ranker():
    ranker = MemoryRanker(decay_constant_lambda=0.1)
    
    # Candidates list
    candidates = [
        {"event": "User configured UART protocol details.", "importance": 0.9, "unix_time": int(time.time())},
        {"event": "User discussed coffee break.", "importance": 0.2, "unix_time": int(time.time()) - 100}
    ]
    
    ranked = ranker.rank_memories(query="UART protocol", candidates=candidates)
    
    assert len(ranked) == 2
    # First item should be UART event due to high relevance & importance
    assert "UART" in ranked[0]["text"]
    assert ranked[0]["score"] > ranked[1]["score"]

def test_memory_retriever_and_writer():
    ep_file = "/tmp/t_episodic.jsonl"
    sem_file = "/tmp/t_semantic.jsonl"
    for f in [ep_file, sem_file]:
        if os.path.exists(f):
            os.remove(f)
            
    wm = WorkingMemory()
    ep = EpisodicMemory(filepath=ep_file)
    sem = SemanticMemory(filepath=sem_file)
    
    writer = MemoryWriter(wm, ep, sem)
    retriever = MemoryRetriever(wm, ep, sem)
    
    writer.store_episode("User ran tests", importance=0.8)
    writer.store_fact("User", "preference", "Telugu explanations")
    
    ctx = retriever.get_context_string("ran tests")
    assert "User ran tests" in ctx
    assert "Telugu explanations" in ctx
    
    for f in [ep_file, sem_file]:
        if os.path.exists(f):
            os.remove(f)

def test_memory_consolidator():
    ep_file = "/tmp/c_episodic.jsonl"
    sem_file = "/tmp/c_semantic.jsonl"
    for f in [ep_file, sem_file]:
        if os.path.exists(f):
            os.remove(f)
            
    ep = EpisodicMemory(filepath=ep_file)
    sem = SemanticMemory(filepath=sem_file)
    
    consolidator = MemoryConsolidator(ep, sem)
    
    # Add multiple milestone episodic records
    ep.add_episode("Completed KM-1 data engine", importance=0.9)
    ep.add_episode("Completed KM-2 synthetic factory", importance=0.9)
    ep.add_episode("Completed KM-3 attention", importance=0.9)
    
    res = consolidator.consolidate()
    
    assert res["consolidated"] is True
    assert "KM-1" in res["summary"]
    assert "KM-2" in res["summary"]
    
    # Redundant logs should have been removed from episodic memory
    assert len(ep.get_all()) == 1 # only contains consolidation summary notification event
    
    # Semantic memory should contain the consolidated fact
    facts = sem.get_all()
    assert len(facts) == 1
    assert facts[0]["relation"] == "completed_milestones"
    
    for f in [ep_file, sem_file]:
        if os.path.exists(f):
            os.remove(f)
