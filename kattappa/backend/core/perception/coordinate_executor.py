"""Coordinate Executor (Program 19.1).

Executes absolute/normalized mouse clicks and keyboard keystrokes using PyAutoGUI.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

import pyautogui

logger = logging.getLogger(__name__)

# Enforce safety failsafe
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


class CoordinateExecutor:
    """Dispatches physical mouse movements, clicks, and keys with failsafes."""

    @classmethod
    def execute_click(cls, x: int, y: int, button: str = "left", clicks: int = 1) -> Dict[str, Any]:
        """Moves mouse and executes mouse click at absolute coordinates (x, y)."""
        try:
            # Boundary checks relative to screen size
            width, height = pyautogui.size()
            if x < 0 or x >= width or y < 0 or y >= height:
                return {
                    "success": False,
                    "error": f"Coordinates ({x}, {y}) out of screen boundaries ({width}x{height})"
                }

            # Move and Click
            pyautogui.moveTo(x, y, duration=0.2)
            pyautogui.click(x, y, button=button, clicks=clicks)
            
            logger.info("CoordinateExecutor: Clicked %s at absolute coordinate (%d, %d)", button, x, y)
            return {
                "success": True,
                "message": f"Clicked {button} at absolute coordinate ({x}, {y})"
            }
        except Exception as e:
            logger.error("CoordinateExecutor: Failed click at (%d, %d) — %s", x, y, e)
            return {"success": False, "error": str(e)}

    @classmethod
    def execute_typing(cls, text: str) -> Dict[str, Any]:
        """Types string text into currently focused input area."""
        try:
            if not text:
                return {"success": True, "message": "Empty text parameter; skipped typing."}

            pyautogui.write(text, interval=0.01)
            logger.info("CoordinateExecutor: Typed string text.")
            return {
                "success": True,
                "message": f"Typed text successful"
            }
        except Exception as e:
            logger.error("CoordinateExecutor: Failed typing — %s", e)
            return {"success": False, "error": str(e)}
