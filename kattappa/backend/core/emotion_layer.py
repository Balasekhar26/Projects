"""Emotion Layer — Phase K17.5.

Tracks the operator's emotional state (Stressed, Frustrated, Calm, Confident)
and dynamically calculates style and pacing adjustments (empathy, detail, delay)
to optimize the interaction.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict

from backend.core.logger import log_event

logger = logging.getLogger(__name__)


class EmotionLayer:
    """Manages emotional adjustments for prompt shaping and pacing."""

    _lock = threading.Lock()
    _user_state: str = "calm"  # calm, stressed, frustrated, confident
    _intensity: float = 0.5

    @classmethod
    def set_user_state(cls, state: str, intensity: float = 0.5) -> None:
        clean_state = state.strip().lower()
        allowed = {"calm", "stressed", "frustrated", "confident"}
        if clean_state not in allowed:
            clean_state = "calm"
        with cls._lock:
            cls._user_state = clean_state
            cls._intensity = max(0.0, min(1.0, intensity))
        log_event("emotion_layer_state_changed", f"User state set to {clean_state} (intensity={intensity:.2f})")

    @classmethod
    def get_style_adjustments(cls) -> Dict[str, Any]:
        """Returns prompt styling weights based on active state."""
        with cls._lock:
            state = cls._user_state
            intensity = cls._intensity

        # Default weights
        adjustments = {
            "empathy_factor": 0.2,
            "verbosity_factor": 1.0,
            "response_delay_seconds": 0.0,
            "explanation_detail": "standard",
        }

        if state == "stressed":
            adjustments["empathy_factor"] = round(0.5 + (intensity * 0.5), 2)
            adjustments["verbosity_factor"] = round(1.0 - (intensity * 0.4), 2)  # shorter answers
            adjustments["explanation_detail"] = "high"
            adjustments["response_delay_seconds"] = round(intensity * 1.5, 2)  # pause before response
        elif state == "frustrated":
            adjustments["empathy_factor"] = round(0.7 + (intensity * 0.3), 2)
            adjustments["verbosity_factor"] = round(1.0 - (intensity * 0.5), 2)  # direct, clear
            adjustments["explanation_detail"] = "concise"
            adjustments["response_delay_seconds"] = 0.0
        elif state == "confident":
            adjustments["empathy_factor"] = 0.1
            adjustments["verbosity_factor"] = 1.2
            adjustments["explanation_detail"] = "technical"

        return adjustments

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._user_state = "calm"
            cls._intensity = 0.5
