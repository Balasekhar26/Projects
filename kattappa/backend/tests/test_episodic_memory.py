import pytest
import time
import tempfile
from datetime import datetime, timedelta
from backend.core.memory.memory_store import MemoryStore
from backend.core.episodic.episode_store import EpisodeStore
from backend.core.episodic.event_segmenter import EventSegmenter
from backend.core.episodic.lesson_extractor import LessonExtractor
from backend.core.episodic.episodic_memory_engine import EpisodicMemoryEngine

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_episodic_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_episode_storage_roundtrip() -> None:
    store = EpisodeStore()
    store.save_episode("Install STM32", "success", "")
    store.save_episode("Flash Firmware", "failure", "missing administrator permission")
    
    episodes = store.get_all_episodes()
    assert len(episodes) == 2
    assert episodes[0]["goal"] == "Flash Firmware"
    assert episodes[1]["goal"] == "Install STM32"

def test_event_segmentation() -> None:
    now = datetime.now()
    
    # 3 episodes: 2 in session 1, 1 in session 2 (elapsed delta > 5 mins)
    episodes = [
        {"goal": "g1", "created_at": (now - timedelta(minutes=10)).isoformat(), "result": "success", "failure_reason": ""},
        {"goal": "g2", "created_at": (now - timedelta(minutes=9)).isoformat(), "result": "success", "failure_reason": ""},
        {"goal": "g3", "created_at": now.isoformat(), "result": "success", "failure_reason": ""}
    ]
    
    segments = EventSegmenter.segment_events(episodes, segment_threshold_sec=300.0)
    assert len(segments) == 2
    assert len(segments[0]) == 2
    assert segments[0][0]["goal"] == "g1"
    assert segments[1][0]["goal"] == "g3"

def test_lesson_extraction_rules() -> None:
    episodes = [
        {"goal": "g1", "result": "failure", "failure_reason": "missing administrator permission"},
        {"goal": "g2", "result": "failure", "failure_reason": "missing administrator permission"},
        {"goal": "g3", "result": "success", "failure_reason": ""}
    ]
    
    lessons = LessonExtractor.extract_lessons(episodes, threshold_count=2)
    assert len(lessons) == 1
    assert "elevation" in lessons[0] or "administrator" in lessons[0]

def test_memory_engine_coordination(test_db_setup) -> None:
    engine = EpisodicMemoryEngine()
    engine.record_episode("Install MCU", "failure", "missing administrator permission")
    engine.record_episode("Setup GCC", "failure", "missing administrator permission")
    
    guidelines = engine.extract_guidelines(threshold_count=2)
    assert len(guidelines) == 1
    assert "elevation" in guidelines[0] or "administrator" in guidelines[0]
