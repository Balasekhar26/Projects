import pytest
from datetime import datetime
from backend.core.vision.ui_element import UIElement
from backend.core.vision.spatial_engine import SpatialRelationshipEngine
from backend.core.vision.attention_engine import AttentionEngine

def test_ui_element_hierarchical_fields() -> None:
    elem = UIElement(
        element_id="el_button",
        text="Click",
        element_type="button",
        confidence=0.95,
        monitor_id=1,
        role="button",
        window_id="win_main",
        parent_id="el_panel",
        children_ids=["sub_label"]
    )
    
    assert elem.parent_id == "el_panel"
    assert "sub_label" in elem.children_ids
    assert elem.observation_count == 1
    assert isinstance(elem.first_seen, datetime)

def test_spatial_relationships_computation() -> None:
    # Set up elements:
    # A at top-left: x1=0, y1=0, x2=100, y2=100 (width=100, height=100)
    # B below A: x1=0, y1=150, x2=100, y2=250 (width=100, height=100)
    # C right of A: x1=150, y1=0, x2=250, y2=100 (width=100, height=100)
    # D inside A: x1=10, y1=10, x2=90, y2=90 (width=80, height=80)
    
    elem_a = UIElement("A", "Block A", "container", 1.0, 1, pixel_bbox=(0, 0, 100, 100))
    elem_b = UIElement("B", "Block B", "container", 1.0, 1, pixel_bbox=(0, 150, 100, 250))
    elem_c = UIElement("C", "Block C", "container", 1.0, 1, pixel_bbox=(150, 0, 250, 100))
    elem_d = UIElement("D", "Block D", "container", 1.0, 1, pixel_bbox=(10, 10, 90, 90))
    elem_e = UIElement("E", "Block E", "container", 1.0, 1, pixel_bbox=(50, 0, 150, 100)) # 50% overlap
    elem_f = UIElement("F", "Block F", "container", 1.0, 1, pixel_bbox=(80, 0, 180, 100)) # 20% overlap
    
    elements = [elem_a, elem_b, elem_c, elem_d, elem_e, elem_f]
    rels = SpatialRelationshipEngine.compute_spatial_relations(elements)
    
    # 1. Assert A contains D
    contains_rels = [r for r in rels if r["predicate"] == "CONTAINS"]
    assert any(r["source_id"] == "A" and r["target_id"] == "D" for r in contains_rels)
    
    # 2. Assert A partially contains E
    partial_rels = [r for r in rels if r["predicate"] == "PARTIALLY_CONTAINS"]
    assert any(r["source_id"] == "A" and r["target_id"] == "E" for r in partial_rels)
    
    # 3. Assert A overlaps F
    overlaps_rels = [r for r in rels if r["predicate"] == "OVERLAPS"]
    assert any(r["source_id"] == "A" and r["target_id"] == "F" for r in overlaps_rels)
    
    # 2. Assert A is ABOVE B
    above_rels = [r for r in rels if r["predicate"] == "ABOVE"]
    assert any(r["source_id"] == "A" and r["target_id"] == "B" for r in above_rels)
    
    # 3. Assert B is BELOW A
    below_rels = [r for r in rels if r["predicate"] == "BELOW"]
    assert any(r["source_id"] == "B" and r["target_id"] == "A" for r in below_rels)
    
    # 4. Assert A is LEFT_OF C
    left_rels = [r for r in rels if r["predicate"] == "LEFT_OF"]
    assert any(r["source_id"] == "A" and r["target_id"] == "C" for r in left_rels)

def test_attention_engine_throttling() -> None:
    engine = AttentionEngine()
    
    elem_focused = UIElement("el_f", "Focused", "button", 1.0, 1, window_id="win_main")
    elem_bg = UIElement("el_bg", "Background", "button", 1.0, 1, window_id="win_bg")
    elem_dialog = UIElement("el_d", "Dialog option", "button", 1.0, 1, window_id="dialog_1")
    
    elements = [elem_focused, elem_bg, elem_dialog]
    
    # Scenario 1: No focus set (returns all elements)
    res1 = engine.filter_elements(elements)
    assert len(res1) == 3
    
    # Scenario 2: Main window focused (filters out background and dialog)
    engine.set_focus(window_id="win_main")
    res2 = engine.filter_elements(elements)
    assert len(res2) == 1
    assert res2[0].element_id == "el_f"
    
    # Scenario 3: Dialog active (filters out win_main and background)
    engine.set_focus(window_id="win_main", dialog_id="dialog_1")
    res3 = engine.filter_elements(elements)
    assert len(res3) == 1
    assert res3[0].element_id == "el_d"
