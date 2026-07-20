import pytest
import os
import tempfile
import numpy as np
from backend.core.memory.memory_store import MemoryStore
from backend.core.vision.object_detector import ObjectDetector
from backend.core.vision.ocr_extractor import OCRExtractor
from backend.core.vision.screen_grounder import ScreenGrounder
from backend.core.vision.visual_indexer import VisualIndexer
from backend.core.vision.vision_engine import VisionEngine

@pytest.fixture(autouse=True)
def test_db_setup(monkeypatch):
    temp_dir = tempfile.mkdtemp(prefix="kattappa_vision_test_")
    monkeypatch.setenv("KATTAPPA_ROOT", temp_dir)
    monkeypatch.setenv("KATTAPPA_TEST_MODE", "true")
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    MemoryStore.clear_database()
    yield temp_dir
    MemoryStore.clear_database()

def test_object_detector_predictions() -> None:
    detector = ObjectDetector()
    results = detector.detect_objects(b"dummy_bytes")
    
    assert len(results) >= 2
    assert results[0]["label"] == "button"
    assert len(results[0]["box"]) == 4

def test_ocr_text_extraction() -> None:
    ocr = OCRExtractor()
    results = ocr.extract_text(b"dummy_bytes")
    
    assert len(results) >= 2
    assert results[0]["text"] == "Kattappa"
    assert len(results[0]["box"]) == 4

def test_screen_grounder_coordinates() -> None:
    detections = [
        {"label": "button", "box": [100, 100, 200, 200]}
    ]
    ocr_results = [
        {"text": "Login", "box": [300, 300, 400, 400]}
    ]
    
    # Check text priority match
    coords = ScreenGrounder.ground_selector("Login", detections, ocr_results)
    assert coords == (350, 350)
    
    # Check label match fallback
    coords_fallback = ScreenGrounder.ground_selector("button", detections, ocr_results)
    assert coords_fallback == (150, 150)
    
    # Unknown selector returns None
    assert ScreenGrounder.ground_selector("cancel", detections, ocr_results) is None

def test_visual_indexer_clip_search(test_db_setup) -> None:
    indexer = VisualIndexer()
    
    # Index mock screenshots
    emb1 = indexer.index_snapshot("snap_1", "path/to/snap1.png", b"data1")
    emb2 = indexer.index_snapshot("snap_2", "path/to/snap2.png", b"data2")
    
    # Query with snap_1 representation vectors
    results = indexer.search_snapshots(emb1, top_k=2)
    
    assert len(results) == 2
    assert results[0]["id"] == "snap_1"
    assert results[0]["score"] > 0.99  # cosine self-match should yield 1.0

def test_vision_engine_orchestration() -> None:
    engine = VisionEngine()
    coords = engine.ground_selector("Kattappa", b"dummy_bytes")
    # "Kattappa" OCR text bounding box is [100, 100, 180, 120] -> center = (140, 110)
    assert coords == (140, 110)

def test_ui_element_and_visual_working_memory() -> None:
    from backend.core.vision.ui_element import UIElement
    from backend.core.vision.visual_working_memory import VisualWorkingMemory
    
    elem = UIElement(
        element_id="el_1",
        text="Submit Invoice",
        element_type="button",
        confidence=0.98,
        monitor_id=1,
        x_norm=0.425,
        y_norm=0.613,
        width_norm=0.1,
        height_norm=0.04,
        x_px=816,
        y_px=662,
        width_px=192,
        height_px=43
    )
    
    assert elem.x_px == 816
    assert elem.text == "Submit Invoice"
    
    memory = VisualWorkingMemory(max_snapshots=2)
    memory.add_snapshot("path/to/snap1.png", [elem])
    
    # Check retrieval
    latest = memory.get_latest_elements()
    assert len(latest) == 1
    assert latest[0].element_id == "el_1"
    
    # Check text query searches
    match = memory.find_element_by_text("invoice")
    assert match is not None
    assert match.element_id == "el_1"
    
    # Overflow check
    elem2 = UIElement("el_2", "Click here", "link", 0.90, 1, 0, 0, 0, 0, 0, 0, 0, 0)
    memory.add_snapshot("path/to/snap2.png", [elem2])
    memory.add_snapshot("path/to/snap3.png", [])
    
    # Snapshot 1 should have been popped
    assert len(memory.snapshots) == 2
    assert memory.find_element_by_text("invoice") is None
