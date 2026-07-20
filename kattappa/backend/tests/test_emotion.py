import pytest
from backend.core.emotion.emotion_detector import EmotionDetector
from backend.core.emotion.affect_tracker import AffectTracker
from backend.core.emotion.empathy_model import EmpathyModel
from backend.core.emotion.emotion_engine import EmotionEngine

def test_emotion_detector_valence() -> None:
    # Negative valence
    assert EmotionDetector.detect_valence("This is completely wrong and broken.") == -0.80
    # Positive valence
    assert EmotionDetector.detect_valence("Perfect, that is great!") == 0.80
    # Neutral valence
    assert EmotionDetector.detect_valence("Show files listing.") == 0.0

def test_affect_tracker_rolling_averages() -> None:
    tracker = AffectTracker()
    
    # 1. Update first time: 0.0 * 0.7 + (-0.8) * 0.3 = -0.24
    v1 = tracker.update_affect(-0.80)
    assert pytest.approx(v1) == -0.24
    
    # 2. Update second time: -0.24 * 0.7 + (-0.8) * 0.3 = -0.168 - 0.24 = -0.408
    v2 = tracker.update_affect(-0.80)
    assert pytest.approx(v2) == -0.408

def test_empathy_model_styling_adaptations() -> None:
    # Frustrated user: valence < -0.3
    style_frustrated = EmpathyModel.get_style_recommendations(-0.5)
    assert style_frustrated["tone"] == "direct_and_helpful"
    assert style_frustrated["apology_needed"] is True
    
    # Happy user: valence > 0.3
    style_happy = EmpathyModel.get_style_recommendations(0.6)
    assert style_happy["tone"] == "warm_and_acknowledging"
    assert style_happy["apology_needed"] is False

def test_emotion_engine_coordination() -> None:
    engine = EmotionEngine()
    
    res = engine.process_user_input("This run is failing with wrong path errors.")
    assert res["input_valence"] == -0.80
    # Rolling average: 0.0 * 0.7 + (-0.8) * 0.3 = -0.24
    assert pytest.approx(res["aggregate_mood"]) == -0.24
    # -0.24 is not yet < -0.30, so professional tone should remain
    assert res["style_guidelines"]["tone"] == "neutral_professional"
    
    # Second consecutive negative input should trigger empathetic adjustments
    res2 = engine.process_user_input("Again, it fails.")
    assert pytest.approx(res2["aggregate_mood"]) == -0.408
    assert res2["style_guidelines"]["tone"] == "direct_and_helpful"
    assert res2["style_guidelines"]["apology_needed"] is True
