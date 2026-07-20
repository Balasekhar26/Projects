import pytest
from backend.core.user_model.preference_tracker import PreferenceTracker
from backend.core.user_model.behavior_pattern_detector import BehaviorPatternDetector
from backend.core.user_model.intent_predictor import IntentPredictor
from backend.core.user_model.user_model_engine import UserModelEngine


def test_preference_ranking() -> None:
    tracker = PreferenceTracker()
    tracker.record_preference("editor", "vscode", weight=3.0)
    tracker.record_preference("editor", "vim", weight=1.0)
    tracker.record_preference("editor", "vscode", weight=2.0)

    ranked = tracker.get_ranked_preferences("editor")
    assert ranked[0] == ("vscode", 5.0)
    assert ranked[1] == ("vim", 1.0)
    assert tracker.get_top_preference("editor") == "vscode"
    assert tracker.get_top_preference("nonexistent") is None


def test_behavior_pattern_detection() -> None:
    detector = BehaviorPatternDetector()
    # Simulate a repeated workflow: open_vscode -> run_pytest (3 times)
    for _ in range(3):
        detector.record_action("open_vscode")
        detector.record_action("run_pytest")

    patterns = detector.detect_patterns(window_size=2, min_occurrences=2)
    pattern_seqs = [p[0] for p in patterns]
    assert ("open_vscode", "run_pytest") in pattern_seqs


def test_intent_prediction() -> None:
    detector = BehaviorPatternDetector()
    # Build history: after "open_vscode", user usually does "run_pytest"
    for _ in range(5):
        detector.record_action("open_vscode")
        detector.record_action("run_pytest")
    detector.record_action("open_vscode")
    detector.record_action("git_commit")

    predictor = IntentPredictor(detector)
    predictions = predictor.predict_next_actions("open_vscode", top_k=3)
    assert predictions[0] == "run_pytest"  # 5 occurrences vs 1


def test_user_model_engine_orchestration() -> None:
    engine = UserModelEngine()

    # Record preferences
    engine.record_choice("browser", "chrome", weight=4.0)
    engine.record_choice("browser", "firefox", weight=1.0)
    assert engine.get_top_preference("browser") == "chrome"

    # Build behavior history
    for _ in range(4):
        engine.observe_action("open_terminal")
        engine.observe_action("activate_venv")

    predictions = engine.predict_next("open_terminal", top_k=2)
    assert "activate_venv" in predictions
