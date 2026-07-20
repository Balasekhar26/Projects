from backend.core.emotion.emotion_detector import EmotionDetector
from backend.core.emotion.affect_tracker import AffectTracker
from backend.core.emotion.empathy_model import EmpathyModel

class EmotionEngine:
    def __init__(self):
        self.detector = EmotionDetector()
        self.tracker = AffectTracker()
        self.empathy = EmpathyModel()

    def process_user_input(self, text: str) -> dict:
        """Processes user dialogue input, updates affect, and yields dialogue styling guide."""
        valence = self.detector.detect_valence(text)
        current_mood = self.tracker.update_affect(valence)
        recommendations = self.empathy.get_style_recommendations(current_mood)
        
        return {
            "input_valence": valence,
            "aggregate_mood": current_mood,
            "style_guidelines": recommendations
        }
