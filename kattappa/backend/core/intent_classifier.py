from __future__ import annotations
from typing import Any, Dict

class IntentClassifier:
    """Classifies user queries into distinct cognitive intents to configure task goals."""

    @staticmethod
    def classify(user_input: str) -> Dict[str, Any]:
        lower_input = user_input.lower().strip()
        intent = "general_task"
        confidence = 0.95

        if "meeting" in lower_input or "schedule" in lower_input or "book" in lower_input:
            intent = "schedule_meeting"
        elif "install" in lower_input:
            intent = "install_software"
        elif "verify" in lower_input or "version" in lower_input:
            intent = "verify_installation"
        elif "log" in lower_input or "analyze" in lower_input or "summarize" in lower_input:
            intent = "summarize_logs"

        return {
            "intent": intent,
            "confidence": confidence,
            "user_request": user_input
        }
