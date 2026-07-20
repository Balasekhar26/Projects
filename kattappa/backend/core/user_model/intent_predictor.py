from backend.core.user_model.behavior_pattern_detector import BehaviorPatternDetector

class IntentPredictor:
    def __init__(self, detector: BehaviorPatternDetector):
        self._detector = detector

    def predict_next_actions(self, current_action: str, top_k: int = 3) -> list[str]:
        """Predicts likely next actions based on what historically followed current_action."""
        history = self._detector._history
        followers: dict[str, int] = {}

        for i in range(len(history) - 1):
            if history[i] == current_action:
                nxt = history[i + 1]
                followers[nxt] = followers.get(nxt, 0) + 1

        ranked = sorted(followers.items(), key=lambda x: x[1], reverse=True)
        return [action for action, _ in ranked[:top_k]]
