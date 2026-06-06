from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass

from backend.core.config import load_config


@dataclass(frozen=True)
class FeatureSupport:
    feature: str
    status: str
    adapter: str
    setup_hint: str
    notes: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "feature": self.feature,
            "status": self.status,
            "adapter": self.adapter,
            "setup_hint": self.setup_hint,
            "notes": self.notes,
        }


def platform_support_report() -> dict[str, object]:
    system = platform.system() or "Unknown"
    lower = system.lower()
    config = load_config()
    commands = _command_map()
    features = [
        FeatureSupport(
            "backend_api",
            "supported",
            "FastAPI + Python",
            "Python 3.10+ and pip",
            "Core backend is OS neutral.",
        ),
        FeatureSupport(
            "desktop_ui",
            "supported",
            "Tauri + React",
            _tauri_hint(lower),
            "Builds on each target OS with that OS's native Tauri prerequisites.",
        ),
        FeatureSupport(
            "local_llm_chat",
            "ready",
            "Built-in local fallback + optional Ollama",
            "Optional upgrade: install Ollama and pull at least one configured model.",
            "Kattappa AI OS starts green without Ollama; local templates, memory, and specialist fallbacks remain available.",
        ),
        FeatureSupport(
            "browser_automation",
            "ready",
            "Playwright Chromium optional adapter",
            "Optional upgrade: run python -m playwright install chromium.",
            "Browser tasks degrade to planning/guide mode when the adapter is unavailable.",
        ),
        FeatureSupport(
            "screen_capture",
            "ready",
            "mss + Pillow optional adapter",
            "Optional upgrade: " + _screen_hint(lower),
            "Screen tasks stay in guide mode when native capture permission or packages are unavailable.",
        ),
        FeatureSupport(
            "ocr",
            "ready",
            "pytesseract + Tesseract OCR optional adapter",
            "Optional upgrade: " + _ocr_hint(lower),
            "Screenshot reading still works as capture-only when OCR is not installed.",
        ),
        FeatureSupport(
            "speech_output",
            "ready",
            _tts_adapter(lower, commands),
            "Optional upgrade: " + _tts_hint(lower),
            "Text chat remains ready when speech output is unavailable.",
        ),
        FeatureSupport(
            "speech_to_text",
            "ready",
            "faster-whisper optional adapter",
            "Optional upgrade: install faster-whisper and keep a small/medium Whisper model available.",
            "Typed chat remains ready when speech-to-text is unavailable.",
        ),
        FeatureSupport(
            "desktop_control",
            "ready",
            _desktop_adapter(lower),
            "Safe default: " + _desktop_hint(lower),
            (
                "Desktop action is green but gated. It stays in observe/guide mode until "
                "SEKHAR_DESKTOP_ENABLED=true and the user approves risky actions."
            ),
        ),
        FeatureSupport(
            "finance_brain",
            "supported",
            "Kattappa AI OS OHLCV baseline + optional Kronos adapter",
            "Feed CSV/API OHLCV candles. Kronos is optional for stronger finance experiments.",
            "Market predictions are uncertain and must not be treated as guaranteed signals.",
        ),
        FeatureSupport(
            "huge_model_lab",
            "ready",
            "AirLLM optional lab",
            "Optional upgrade: pip install airllm torch bitsandbytes, then use the AirLLM lab endpoint explicitly.",
            "Fits larger models on low VRAM, but usually does not make normal chat faster.",
        ),
        FeatureSupport(
            "local_file_transfer",
            "ready",
            "LocalSend optional adapter",
            "Optional upgrade: install LocalSend if you want Kattappa AI OS setup notes to point at local device file transfer.",
            "Optional convenience only; Kattappa AI OS core does not require it.",
        ),
    ]
    return {
        "os": {
            "system": system,
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "commands": commands,
        "features": [feature.as_dict() for feature in features],
        "promise": (
            "Kattappa AI OS keeps the same feature surface on Windows, macOS, and Linux. "
            "Optional native OS adapters can improve capability, but unavailable adapters "
            "degrade safely and stay green instead of preventing startup."
        ),
    }


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _command_map() -> dict[str, bool]:
    names = [
        "ollama",
        "npm",
        "node",
        "tesseract",
        "say",
        "spd-say",
        "espeak",
        "localsend",
        "localsend_app",
    ]
    return {name: shutil.which(name) is not None for name in names}


def _tauri_hint(system: str) -> str:
    if system == "windows":
        return "Install Node.js, Rust, and Microsoft Visual Studio Build Tools."
    if system == "darwin":
        return "Install Node.js, Rust, Xcode Command Line Tools, and WebKit support from Tauri prerequisites."
    if system == "linux":
        return "Install Node.js, Rust, webkit2gtk, appindicator, librsvg, and build-essential packages."
    return "Install Node.js, Rust, and native Tauri prerequisites for this OS."


def _screen_hint(system: str) -> str:
    if system == "darwin":
        return "Grant Screen Recording permission to the terminal or packaged app."
    if system == "linux":
        return "Use an X11/Wayland session that allows screenshots; install mss and Pillow."
    return "Install mss and Pillow."


def _ocr_hint(system: str) -> str:
    if system == "windows":
        return "Install Tesseract OCR and add it to PATH."
    if system == "darwin":
        return "Install Tesseract, for example with brew install tesseract."
    if system == "linux":
        return "Install the tesseract-ocr package from your distribution."
    return "Install Tesseract OCR and pytesseract."


def _tts_ready(system: str, commands: dict[str, bool]) -> bool:
    return (
        _module_available("pyttsx3")
        or (system == "darwin" and commands["say"])
        or (system == "linux" and (commands["spd-say"] or commands["espeak"]))
        or (system == "windows" and shutil.which("powershell") is not None)
    )


def _tts_adapter(system: str, commands: dict[str, bool]) -> str:
    if _module_available("pyttsx3"):
        return "pyttsx3"
    if system == "darwin" and commands["say"]:
        return "macOS say"
    if system == "linux" and commands["spd-say"]:
        return "Speech Dispatcher"
    if system == "linux" and commands["espeak"]:
        return "eSpeak"
    if system == "windows":
        return "Windows System.Speech"
    return "not configured"


def _tts_hint(system: str) -> str:
    if system == "darwin":
        return "No extra package is usually needed for say; pyttsx3 is optional."
    if system == "linux":
        return "Install speech-dispatcher or espeak for native speech fallback."
    if system == "windows":
        return "Windows speech is built in; pyttsx3 is optional."
    return "Install pyttsx3 or a native speech command."


def _desktop_adapter(system: str) -> str:
    if system == "darwin":
        return "pyautogui + macOS Accessibility"
    if system == "linux":
        return "pyautogui + X11/Wayland permissions"
    if system == "windows":
        return "pyautogui + Windows UI automation"
    return "pyautogui"


def _desktop_hint(system: str) -> str:
    if system == "darwin":
        return "Install pyautogui and grant Accessibility permission."
    if system == "linux":
        return "Install pyautogui and a session backend that allows keyboard/mouse control."
    return (
        "Install pyautogui and enable SEKHAR_DESKTOP_ENABLED=true only after testing."
    )
