import pyautogui
from typing import Tuple
from backend.core.obsidian_memory import ObsidianMemory

# Ensure failsafe corner trigger is active
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.5

class ComputerControl:
    def __init__(self) -> None:
        self.memory = ObsidianMemory()

    def get_screen_size(self) -> Tuple[int, int]:
        return pyautogui.size()

    def _resolve_coordinates(self, x_norm: float, y_norm: float) -> Tuple[int, int]:
        """Converts normalized 0-1000 coordinates to actual pixel coordinates."""
        width, height = self.get_screen_size()
        x = int((x_norm / 1000.0) * width)
        y = int((y_norm / 1000.0) * height)
        # Clamp coordinate bounds
        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        return x, y

    def click(self, x_norm: float, y_norm: float, double: bool = False, button: str = "left") -> None:
        """Clicks at normalized 0-1000 coordinates."""
        x, y = self._resolve_coordinates(x_norm, y_norm)
        action_type = "Double-click" if double else "Click"
        log_msg = f"{action_type} at screen pixels ({x}, {y}) [normalized [{x_norm:.1f}, {y_norm:.1f}]] using {button} button."
        
        try:
            self.memory.write_daily_note(content=log_msg, category="gui-control")
            if double:
                pyautogui.doubleClick(x, y, button=button)
            else:
                pyautogui.click(x, y, button=button)
        except pyautogui.FailSafeException:
            abort_msg = "GUI action aborted due to fail-safe trigger (mouse moved to corner)."
            self.memory.write_daily_note(content=abort_msg, category="error")
            raise RuntimeError(abort_msg)

    def type_text(self, text: str, press_enter: bool = False) -> None:
        """Types text at the current cursor location."""
        log_msg = f"Type text: '{text}' (Press Enter: {press_enter})"
        try:
            self.memory.write_daily_note(content=log_msg, category="gui-control")
            pyautogui.write(text, interval=0.05)
            if press_enter:
                pyautogui.press("enter")
        except pyautogui.FailSafeException:
            abort_msg = "GUI action aborted due to fail-safe trigger (mouse moved to corner)."
            self.memory.write_daily_note(content=abort_msg, category="error")
            raise RuntimeError(abort_msg)

    def press_key(self, key: str) -> None:
        """Presses a single keyboard key."""
        log_msg = f"Press key: '{key}'"
        try:
            self.memory.write_daily_note(content=log_msg, category="gui-control")
            pyautogui.press(key)
        except pyautogui.FailSafeException:
            abort_msg = "GUI action aborted due to fail-safe trigger (mouse moved to corner)."
            self.memory.write_daily_note(content=abort_msg, category="error")
            raise RuntimeError(abort_msg)

    def hotkey(self, *keys: str) -> None:
        """Executes a hotkey shortcut combination."""
        log_msg = f"Execute hotkey combination: {keys}"
        try:
            self.memory.write_daily_note(content=log_msg, category="gui-control")
            pyautogui.hotkey(*keys)
        except pyautogui.FailSafeException:
            abort_msg = "GUI action aborted due to fail-safe trigger (mouse moved to corner)."
            self.memory.write_daily_note(content=abort_msg, category="error")
            raise RuntimeError(abort_msg)
