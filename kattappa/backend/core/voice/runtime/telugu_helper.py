"""Telugu Voice Optimization (Program 31.0).

Normalizes Telugu + English code-mixed text: translates numeric digits to Telugu
phonetic script and injects appropriate pauses to maximize output synthesis clarity.
"""
from __future__ import annotations

import re

# Digit mapping of Unicode characters
TELUGU_DIGIT_MAP = {
    "0": "సున్నా",
    "1": "ఒకటి",
    "2": "రెండు",
    "3": "మూడు",
    "4": "నాలుగు",
    "5": "ఐదు",
    "6": "ఆరు",
    "7": "ఏడు",
    "8": "ఎనిమిది",
    "9": "తొమ్మిది",
}


class TeluguVoiceHelper:
    """Helper to sanitize mixed language scripts for speech engine parsing."""

    @classmethod
    def translate_digits(cls, text: str) -> str:
        """Replaces standard numeric digits with phonetic Telugu equivalent words."""
        result = []
        for char in text:
            if char in TELUGU_DIGIT_MAP:
                result.append(" " + TELUGU_DIGIT_MAP[char] + " ")
            else:
                result.append(char)
        return "".join(result)

    @classmethod
    def normalize_text(cls, text: str) -> str:
        """Preprocesses mixed code segments for phonetic playback.

        Normalizes punctuation pauses and numbers to Telugu words.
        """
        if not text:
            return ""

        # 1. Translate numeric digits
        normalized = cls.translate_digits(text)

        # 2. Add structural pauses to multi-clause periods (commas, eclipses)
        normalized = normalized.replace("...", " -- ")
        
        # 3. Clean up excessive whitespace
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()
