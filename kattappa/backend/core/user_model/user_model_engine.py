from backend.core.user_model.preference_tracker import PreferenceTracker
from backend.core.user_model.behavior_pattern_detector import BehaviorPatternDetector
from backend.core.user_model.intent_predictor import IntentPredictor

class UserModelEngine:
    def __init__(self):
        self.preferences = PreferenceTracker()
        self.behavior = BehaviorPatternDetector()
        self.intent = IntentPredictor(self.behavior)

    def observe_action(self, action: str) -> None:
        """Records a user action into the behavior history."""
        self.behavior.record_action(action)

    def record_choice(self, category: str, choice: str, weight: float = 1.0) -> None:
        """Records a preference choice."""
        self.preferences.record_preference(category, choice, weight)

    def predict_next(self, current_action: str, top_k: int = 3) -> list[str]:
        """Predicts likely next user actions from history."""
        return self.intent.predict_next_actions(current_action, top_k)

    def get_top_preference(self, category: str) -> str | None:
        """Returns user's top preference for a category."""
        return self.preferences.get_top_preference(category)
