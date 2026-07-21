"""Emotion-Aware Speech Synthesis (Program 31.0).

Scans textual prompt responses for emotional context tags and maps them to
synthesis speed/scale parameters to match dialogue tone.
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

# Speed/duration settings mapping to emotions (lower length_scale = faster speed)
EMOTION_SPEED_SCALES = {
    "NEUTRAL": {"length_scale": 1.0},
    "HAPPY": {"length_scale": 0.85},     # Speak slightly faster/excited
    "SAD": {"length_scale": 1.25},       # Speak slower/somber
    "ANGRY": {"length_scale": 0.80},     # Speak faster/intense
    "SURPRISED": {"length_scale": 0.90},  # Speak excited
    "FEAR": {"length_scale": 0.95},
}


class EmotionTTSManager:
    """Extracts tag headers from response text and resolves emotional speech scales."""

    @classmethod
    def extract_emotion_tag(cls, text: str) -> Tuple[str, str]:
        """Scans text for [EMOTION] prefixes.

        Returns:
            (clean_text, emotion_string)
            Example: "[HAPPY] Welcome back!" -> ("Welcome back!", "HAPPY")
        """
        match = re.match(r"^\[([A-Z_]+)\]\s*(.*)$", text.strip(), re.DOTALL)
        if match:
            emotion = match.group(1).upper()
            clean_text = match.group(2)
            if emotion in EMOTION_SPEED_SCALES:
                return clean_text, emotion
            # Fallback to NEUTRAL if tag is unregistered
            return clean_text, "NEUTRAL"

        # Check for implicit emotion keywords in text if no explicit tag matches
        lower = text.lower()
        if any(w in lower for w in ("yay", "great", "excellent", "happy", "wonderful")):
            return text, "HAPPY"
        if any(w in lower for w in ("alas", "sorry", "sad", "somber", "regret", "fail")):
            return text, "SAD"
        if any(w in lower for w in ("shock", "wow", "amazing", "surprise")):
            return text, "SURPRISED"

        return text, "NEUTRAL"

    @classmethod
    def get_speech_parameters(cls, emotion: str) -> Dict[str, float]:
        """Returns the Piper length_scale parameter values for the emotion."""
        return EMOTION_SPEED_SCALES.get(emotion.upper(), EMOTION_SPEED_SCALES["NEUTRAL"])
