from __future__ import annotations

import platform
import time
from pathlib import Path

from backend.core.config import load_config


def _ensure_enabled() -> None:
    if not load_config().desktop_enabled:
        raise PermissionError(
            "Desktop control is disabled. Enable SEKHAR_DESKTOP_ENABLED=true after testing."
        )


def _pyautogui():
    try:
        import pyautogui
    except Exception as exc:
        raise RuntimeError(
            "Desktop automation is not available on this OS/session. "
            "Universal AI can still run chat, memory, web UI, and non-desktop tools."
        ) from exc
    pyautogui.FAILSAFE = True
    return pyautogui


def type_text(text: str) -> str:
    _ensure_enabled()
    pyautogui = _pyautogui()
    pyautogui.write(text, interval=0.01)
    return "typed"


def press_key(key: str) -> str:
    _ensure_enabled()
    pyautogui = _pyautogui()
    pyautogui.press(key)
    return f"pressed {key}"


def hotkey(*keys: str) -> str:
    _ensure_enabled()
    pyautogui = _pyautogui()
    pyautogui.hotkey(*keys)
    return f"hotkey {'+'.join(keys)}"


def screenshot(path: str | None = None) -> str:
    pyautogui = _pyautogui()
    config = load_config()
    config.screenshots_dir.mkdir(parents=True, exist_ok=True)
    target = Path(path) if path else config.screenshots_dir / "desktop_screen.png"
    image = pyautogui.screenshot()
    image.save(target)
    return str(target)


def open_start_menu() -> str:
    _ensure_enabled()
    pyautogui = _pyautogui()
    system = platform.system().lower()
    if system == "darwin":
        pyautogui.hotkey("command", "space")
        label = "spotlight launcher opened"
    elif system == "linux":
        pyautogui.press("super")
        label = "application launcher opened"
    else:
        pyautogui.press("win")
        label = "start menu opened"
    time.sleep(1)
    return label


def open_app_launcher() -> str:
    return open_start_menu()
