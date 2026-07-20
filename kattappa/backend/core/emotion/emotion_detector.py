import re

class EmotionDetector:
    FRUSTRATION_KEYWORDS = {"wrong", "fail", "bad", "slow", "error", "broken", "stupid", "hate", "fails"}
    SATISFACTION_KEYWORDS = {"thanks", "great", "good", "perfect", "awesome", "love", "excellent"}

    @classmethod
    def detect_valence(cls, text: str) -> float:
        """Analyzes text keywords to return a sentiment valence score between -1.0 and 1.0."""
        cleaned = re.sub(r'[^\w\s]', '', text.lower())
        words = set(cleaned.strip().split())
        
        # Check negative/frustrated sentiment
        if words.intersection(cls.FRUSTRATION_KEYWORDS):
            return -0.80
            
        # Check positive/satisfied sentiment
        if words.intersection(cls.SATISFACTION_KEYWORDS):
            return 0.80
            
        return 0.0
