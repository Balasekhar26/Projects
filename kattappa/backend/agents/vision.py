from __future__ import annotations

from backend.tools.screen_tools import take_screenshot
from backend.agents.vision_agent import VisionAgent


def vision_node(state):
    try:
        screenshot_path = take_screenshot()
        agent = VisionAgent()
        # Query VLM to analyze screen
        x_norm, y_norm, description = agent.locate_element(
            screenshot_path,
            "Analyze the current screen and describe what you see, including key windows, buttons, and layouts."
        )
        state["result"] = description
        state["logs"].append("vision: screen analyzed via VLM")
    except Exception as e:
        # Fallback to OCR ask_model if VLM fails
        from backend.core.model_router import ask_model
        from backend.tools.screen_tools import read_screen_text
        screen_text = read_screen_text()
        state["result"] = ask_model(
            f"Explain the current screen from OCR text and say what action may help.\nOCR:\n{screen_text}",
            role="vision",
        )
        state["logs"].append(f"vision fallback: OCR analysis used due to error: {e}")
    return state
