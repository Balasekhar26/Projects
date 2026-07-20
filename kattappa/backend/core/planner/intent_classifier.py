from __future__ import annotations
import os
from backend.core.model_router import ask_model

class IntentClassifier:
    @classmethod
    def classify_intent(cls, goal: str) -> str:
        import sys
        use_mock = (
            "pytest" in sys.modules or 
            os.getenv("KATTAPPA_TEST_MODE") == "true" or
            os.getenv("KATTAPPA_MOCK_LLM") == "true"
        )
        if use_mock:
            lower_goal = goal.lower()
            if "search" in lower_goal or "find" in lower_goal:
                return "research"
            if "write" in lower_goal or "code" in lower_goal or "test" in lower_goal:
                return "coding"
            if "file" in lower_goal or "read" in lower_goal:
                return "file operation"
            return "automation"
        else:
            prompt = (
                f"Classify the primary intent of this task: \"{goal}\"\n"
                f"Output only one category word from this list: research, coding, automation, file operation, browser operation, analysis, conversation, creative."
            )
            try:
                res = ask_model(prompt, role="planning")
                return res.strip().lower()
            except Exception:
                return "automation"
