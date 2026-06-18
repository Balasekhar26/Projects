from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass
import importlib.util
from pathlib import Path

from backend.core.config import load_config


@dataclass(frozen=True)
class FeatureSupport:
    feature: str
    status: str
    adapter: str
    setup_hint: str
    notes: str = ""
    installed: bool = False
    fallback_available: bool = True
    required: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "feature": self.feature,
            "status": self.status,
            "adapter": self.adapter,
            "setup_hint": self.setup_hint,
            "notes": self.notes,
            "installed": self.installed,
            "fallback_available": self.fallback_available,
            "required": self.required,
            "usable": self.installed or self.fallback_available,
        }


def platform_support_report() -> dict[str, object]:
    system = platform.system() or "Unknown"
    lower = system.lower()
    config = load_config()
    commands = _command_map()
    modules = {
        "playwright": _module_available("playwright"),
        "mss": _module_available("mss"),
        "PIL": _module_available("PIL"),
        "pytesseract": _module_available("pytesseract"),
        "faster_whisper": _module_available("faster_whisper"),
        "openwakeword": _module_available("openwakeword"),
        "pyautogui": _module_available("pyautogui"),
        "pywinauto": _module_available("pywinauto"),
        "airllm": _module_available("airllm"),
    }
    local_llm_installed = commands["ollama"]
    browser_installed = modules["playwright"]
    screen_installed = modules["mss"] and modules["PIL"]
    ocr_installed = modules["pytesseract"] and commands["tesseract"]
    stt_installed = modules["faster_whisper"]
    wake_installed = modules["openwakeword"]
    tts_installed = _tts_ready(lower, commands)
    desktop_installed = modules["pyautogui"] or (lower == "windows" and modules["pywinauto"])
    desktop_status = (
        "disabled"
        if not config.desktop_enabled
        else ("installed" if desktop_installed else "fallback")
    )
    kronos_root = _external_projects_root(config.root) / "Kronos"
    kronos_installed = kronos_root.exists()
    file_transfer_installed = commands["localsend"] or commands["localsend_app"]
    features = [
        FeatureSupport(
            "backend_api",
            "supported",
            "FastAPI + Python",
            "Python 3.10+ and pip",
            "Core backend is OS neutral.",
            installed=True,
        ),
        FeatureSupport(
            "desktop_ui",
            "supported",
            "Tauri + React",
            _tauri_hint(lower),
            "Builds on each target OS with that OS's native Tauri prerequisites.",
            installed=True,
        ),
        FeatureSupport(
            "local_llm_chat",
            "installed" if local_llm_installed else "fallback",
            "Built-in local fallback + optional Ollama",
            "Optional upgrade: install Ollama and pull at least one configured model.",
            "Kattappa AI OS can still answer with local templates, memory, and specialist fallbacks when Ollama is absent.",
            installed=local_llm_installed,
        ),
        FeatureSupport(
            "browser_automation",
            "installed" if browser_installed else "fallback",
            "Playwright Chromium optional adapter",
            "Optional upgrade: run python -m playwright install chromium.",
            "Browser tasks degrade to planning/guide mode when the adapter is unavailable.",
            installed=browser_installed,
        ),
        FeatureSupport(
            "screen_capture",
            "installed" if screen_installed else "fallback",
            "mss + Pillow optional adapter",
            "Optional upgrade: " + _screen_hint(lower),
            "Screen tasks stay in guide mode when native capture permission or packages are unavailable.",
            installed=screen_installed,
        ),
        FeatureSupport(
            "ocr",
            "installed" if ocr_installed else "fallback",
            "pytesseract + Tesseract OCR optional adapter",
            "Optional upgrade: " + _ocr_hint(lower),
            "Screenshot reading still works as capture-only when OCR is not installed.",
            installed=ocr_installed,
        ),
        FeatureSupport(
            "speech_output",
            "installed" if tts_installed else "fallback",
            _tts_adapter(lower, commands),
            "Optional upgrade: " + _tts_hint(lower),
            "Text chat remains ready when speech output is unavailable.",
            installed=tts_installed,
        ),
        FeatureSupport(
            "speech_to_text",
            "installed" if stt_installed else "fallback",
            "faster-whisper optional adapter",
            "Optional upgrade: install faster-whisper and keep a small/medium Whisper model available.",
            "Typed chat remains ready when speech-to-text is unavailable.",
            installed=stt_installed,
        ),
        FeatureSupport(
            "wake_word",
            "installed" if wake_installed else "fallback",
            "openWakeWord optional adapter",
            "Optional upgrade: install openwakeword and configure local wake-name models.",
            "Wake-name commands fall back to local transcript parsing when openWakeWord is unavailable.",
            installed=wake_installed,
        ),
        FeatureSupport(
            "desktop_control",
            desktop_status,
            _desktop_adapter(lower),
            "Safe default: " + _desktop_hint(lower),
            (
                "Desktop action is approval gated. It stays in observe/guide mode until "
                "KATTAPPA_DESKTOP_ENABLED=true and the user approves risky actions."
            ),
            installed=desktop_installed and config.desktop_enabled,
            fallback_available=True,
        ),
        FeatureSupport(
            "finance_brain",
            "supported",
            "Kattappa AI OS OHLCV baseline + optional Kronos adapter",
            "Feed CSV/API OHLCV candles. Kronos is optional for stronger finance experiments.",
            "Market predictions are uncertain and must not be treated as guaranteed signals.",
            installed=True,
        ),
        FeatureSupport(
            "kronos_finance",
            "installed" if kronos_installed else "fallback",
            "Optional Kronos repository adapter",
            f"Optional upgrade: clone Kronos to {kronos_root}.",
            "The owned local OHLCV baseline remains available when Kronos is absent.",
            installed=kronos_installed,
        ),
        FeatureSupport(
            "huge_model_lab",
            "installed" if modules["airllm"] else "fallback",
            "AirLLM optional lab",
            "Optional upgrade: pip install airllm torch bitsandbytes, then use the AirLLM lab endpoint explicitly.",
            "Fits larger models on low VRAM, but usually does not make normal chat faster.",
            installed=modules["airllm"],
        ),
        FeatureSupport(
            "local_file_transfer",
            "installed" if file_transfer_installed else "fallback",
            "LocalSend optional adapter",
            "Optional upgrade: install LocalSend if you want Kattappa AI OS setup notes to point at local device file transfer.",
            "Optional convenience only; Kattappa AI OS core does not require it.",
            installed=file_transfer_installed,
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
            "degrade safely without being reported as installed."
        ),
    }


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


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


def _external_projects_root(root: Path) -> Path:
    projects_root = root.parent
    external_root = projects_root / "external-projects"
    if external_root.exists():
        return external_root
    return projects_root / "bin" / "external-projects"


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
        "Install pyautogui and enable KATTAPPA_DESKTOP_ENABLED=true only after testing."
    )
