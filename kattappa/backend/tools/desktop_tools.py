from __future__ import annotations

import os
import hashlib
import time
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

from backend.core.config import load_config, runtime_data_root


PROTECTED_APPS = {
    "keychain", "credential manager", "password manager", "banking", "wallet",
    "ssh key", "ssh manager", "authentication", "authenticator", "1password", 
    "lastpass", "dashlane", "bitwarden", "keepass", "roboform"
}

APPROVED_APPS = {
    "vs code", "vscode", "terminal", "browser", "chrome", "firefox", "safari", 
    "docker desktop", "docker", "approved engineering tools", "finder", "explorer"
}

PROTECTED_DIRS = {
    "~/.ssh", "~/.aws", "~/.gnupg", "/etc", "/system", "c:\\windows", 
    ".ssh", ".aws", ".gnupg"
}


def _ensure_enabled() -> None:
    if os.environ.get("KATTAPPA_ENV") == "test":
        return
    if not load_config().desktop_enabled:
        raise PermissionError(
            "Desktop control is disabled. Enable KATTAPPA_DESKTOP_ENABLED=true after testing."
        )


def _pyautogui():
    try:
        import pyautogui
    except Exception as exc:
        raise RuntimeError(
            "Desktop automation is not available on this OS/session."
        ) from exc
    pyautogui.FAILSAFE = True
    return pyautogui


def _log_desktop_audit(category: str, action: str, details: dict[str, Any] | None = None) -> None:
    try:
        log_file = Path(runtime_data_root()) / "backend" / "data" / "desktop_audit.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_entry = {
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "category": category,
            "action": action,
            "details": details or {}
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass


def is_protected_directory(path_str: str) -> bool:
    try:
        path = Path(path_str).expanduser().resolve()
        path_str_clean = str(path).lower()
        for pdir in PROTECTED_DIRS:
            resolved_pdir = str(Path(pdir).expanduser().resolve()).lower()
            if resolved_pdir in path_str_clean:
                return True
    except Exception:
        pass
    
    path_str_clean = path_str.lower()
    for pdir in PROTECTED_DIRS:
        if pdir in path_str_clean:
            return True
    return False


def contains_secrets(text: str) -> str | None:
    lower = text.lower()
    secret_triggers = ["api_key", "token", "password", "private_key", "secret", "credential", "auth_token"]
    for tr in secret_triggers:
        if tr in lower:
            return tr
    return None


def is_ui_protected(window_title: str) -> bool:
    lower = window_title.lower()
    protected_words = ["keychain", "password", "bank", "payment", "checkout", "credit card", "security prompt", "authenticate"]
    return any(word in lower for word in protected_words)


def get_active_window() -> str:
    if os.environ.get("KATTAPPA_ENV") == "test":
        return "VS Code"
    try:
        import pygetwindow as gw
        win = gw.getActiveWindow()
        return win.title if win else "VS Code"
    except Exception:
        try:
            system = platform.system().lower()
            if system == "darwin":
                cmd = """osascript -e 'tell application "System Events" to get name of first process whose frontmost is true'"""
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                return res.stdout.strip()
        except Exception:
            pass
        return "VS Code"


def list_open_windows() -> list[str]:
    if os.environ.get("KATTAPPA_ENV") == "test":
        return ["VS Code", "Terminal", "Docker Desktop"]
    try:
        import pygetwindow as gw
        return [win.title for win in gw.getAllWindows() if win.title]
    except Exception:
        return ["VS Code", "Terminal"]


def open_application(app_name: str) -> str:
    _ensure_enabled()
    lower_app = app_name.lower().strip()
    
    if any(app in lower_app for app in PROTECTED_APPS):
        _log_desktop_audit("security", "block_protected_app", {"app_name": app_name})
        raise PermissionError(f"Access to protected application '{app_name}' is strictly prohibited.")
        
    if not any(app in lower_app for app in APPROVED_APPS):
        if os.environ.get("KATTAPPA_ENV") != "test":
            raise PermissionError(f"Access to application '{app_name}' requires human approval.")
        
    _log_desktop_audit("application", "open", {"app_name": app_name})
    if os.environ.get("KATTAPPA_ENV") == "test":
        return f"opened {app_name} (simulated)"
        
    system = platform.system().lower()
    if system == "darwin":
        subprocess.run(["open", "-a", app_name])
    elif system == "windows":
        subprocess.run(["start", app_name], shell=True)
    else:
        subprocess.run([app_name])
    return f"opened {app_name}"


def move_mouse(x_norm: float, y_norm: float) -> str:
    _ensure_enabled()
    width, height = (1920, 1080)
    if os.environ.get("KATTAPPA_ENV") != "test":
        try:
            pyautogui = _pyautogui()
            width, height = pyautogui.size()
        except Exception:
            pass
            
    x = int((x_norm / 1000.0) * width)
    y = int((y_norm / 1000.0) * height)
    
    _log_desktop_audit("mouse", "move", {"x_norm": x_norm, "y_norm": y_norm, "x": x, "y": y})
    if os.environ.get("KATTAPPA_ENV") == "test":
        return f"moved mouse to ({x}, {y}) (simulated)"
        
    pyautogui = _pyautogui()
    pyautogui.moveTo(x, y)
    return f"moved mouse to ({x}, {y})"


def click_element(x_norm: float, y_norm: float, button: str = "left", click_type: str = "single") -> str:
    _ensure_enabled()
    active_win = get_active_window()
    if is_ui_protected(active_win):
        raise PermissionError("GUI Click blocked: Interacting with protected application is prohibited.")
        
    width, height = (1920, 1080)
    if os.environ.get("KATTAPPA_ENV") != "test":
        try:
            pyautogui = _pyautogui()
            width, height = pyautogui.size()
        except Exception:
            pass
            
    x = int((x_norm / 1000.0) * width)
    y = int((y_norm / 1000.0) * height)
    
    _log_desktop_audit("mouse", "click", {"x_norm": x_norm, "y_norm": y_norm, "x": x, "y": y, "button": button, "click_type": click_type})
    
    if os.environ.get("KATTAPPA_ENV") == "test":
        return f"clicked {button} {click_type} at ({x}, {y}) (simulated)"
        
    pyautogui = _pyautogui()
    double = (click_type == "double")
    if double:
        pyautogui.doubleClick(x, y, button=button)
    else:
        pyautogui.click(x, y, button=button)
    return f"clicked {button} {click_type} at ({x}, {y})"


def type_text(text: str) -> str:
    _ensure_enabled()
    active_win = get_active_window()
    if is_ui_protected(active_win):
        raise PermissionError("Keyboard control blocked: Interacting with protected application is prohibited.")
        
    match = contains_secrets(text)
    if match:
        raise PermissionError(f"Keyboard control blocked: Typing or pasting secrets ({match}) is prohibited.")
        
    _log_desktop_audit("keyboard", "type_text", {"text": text})
    if os.environ.get("KATTAPPA_ENV") == "test":
        return f"typed {text} (simulated)"
        
    pyautogui = _pyautogui()
    pyautogui.write(text, interval=0.01)
    return "typed"


def press_key(key: str) -> str:
    _ensure_enabled()
    active_win = get_active_window()
    if is_ui_protected(active_win):
        raise PermissionError("Keyboard control blocked: Interacting with protected application is prohibited.")
        
    _log_desktop_audit("keyboard", "press_key", {"key": key})
    if os.environ.get("KATTAPPA_ENV") == "test":
        return f"pressed {key} (simulated)"
        
    pyautogui = _pyautogui()
    pyautogui.press(key)
    return f"pressed {key}"


def hotkey(*keys: str) -> str:
    _ensure_enabled()
    active_win = get_active_window()
    if is_ui_protected(active_win):
        raise PermissionError("Keyboard control blocked: Interacting with protected application is prohibited.")
        
    _log_desktop_audit("keyboard", "hotkey", {"keys": keys})
    if os.environ.get("KATTAPPA_ENV") == "test":
        return f"hotkey {'+'.join(keys)} (simulated)"
        
    pyautogui = _pyautogui()
    pyautogui.hotkey(*keys)
    return f"hotkey {'+'.join(keys)}"


def take_screenshot(path: str | None = None) -> dict[str, Any]:
    config = load_config()
    if not os.environ.get("KATTAPPA_ENV") == "test" and not config.screen_capture_enabled:
        raise PermissionError(
            "Screen capture is disabled until setup enables KATTAPPA_SCREEN_CAPTURE_ENABLED=true."
        )
        
    active_win = get_active_window()
    if is_ui_protected(active_win):
        raise PermissionError("Screen capture blocked: Screenshotting protected window is prohibited.")
        
    screenshots_dir = config.screenshots_dir if not os.environ.get("KATTAPPA_ENV") == "test" else Path(runtime_data_root()) / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    target = Path(path) if path else screenshots_dir / f"screenshot_{int(time.time())}.png"
    
    if os.environ.get("KATTAPPA_ENV") == "test":
        target.write_text("simulated image content", encoding="utf-8")
    else:
        try:
            import pyautogui
            image = pyautogui.screenshot()
            image.save(target)
        except Exception:
            import mss
            from PIL import Image
            capture_factory = getattr(mss, "MSS", mss.mss)
            with capture_factory() as capture:
                monitor = capture.monitors[1]
                image = capture.grab(monitor)
                Image.frombytes("RGB", image.size, image.rgb).save(target)
                
    # Calculate checksum
    sha256_hash = hashlib.sha256()
    with open(target, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    checksum = sha256_hash.hexdigest()
    
    meta = {
        "path": str(target),
        "timestamp": time.time(),
        "sha256": checksum,
        "window": active_win
    }
    
    _log_desktop_audit("screenshot", "capture", meta)
    return meta


def read_screen() -> dict[str, Any]:
    active_win = get_active_window()
    if is_ui_protected(active_win):
        raise PermissionError("Screen reading blocked: Accessing protected window is prohibited.")
        
    meta = take_screenshot()
    screenshot_path = meta["path"]
    
    text = ""
    words = []
    if os.environ.get("KATTAPPA_ENV") == "test":
        text = "This is a simulated screen containing VS Code elements."
        words = [{"text": "VS Code", "left": 10, "top": 10, "width": 50, "height": 20, "confidence": 99}]
    else:
        try:
            import pytesseract
            from PIL import Image
            text = pytesseract.image_to_string(Image.open(screenshot_path)).strip()
            
            from pytesseract import Output
            image = Image.open(screenshot_path)
            data = pytesseract.image_to_data(image, output_type=Output.DICT)
            for index, w_text in enumerate(data.get("text", [])):
                clean = str(w_text).strip()
                if not clean:
                    continue
                try:
                    confidence = int(float(data["conf"][index]))
                except Exception:
                    confidence = -1
                if confidence >= 0:
                    words.append({
                        "text": clean,
                        "left": int(data["left"][index]),
                        "top": int(data["top"][index]),
                        "width": int(data["width"][index]),
                        "height": int(data["height"][index]),
                        "confidence": confidence,
                    })
        except Exception as e:
            text = f"OCR failed: {e}"
            
    res = {
        "window": active_win,
        "elements": words,
        "text": text,
        "screenshot_path": screenshot_path,
        "timestamp": time.time(),
        "provenance": "UNTRUSTED_UI_DATA"
    }
    
    return res


def open_app_launcher() -> str:
    _ensure_enabled()
    _log_desktop_audit("application", "open_launcher")
    system = platform.system().lower()
    pyautogui = _pyautogui()
    if system == "darwin":
        pyautogui.hotkey("command", "space")
        return "spotlight launcher opened"
    elif system == "windows":
        pyautogui.press("win")
        return "start menu opened"
    else:
        pyautogui.press("win")
        return "app launcher opened"
