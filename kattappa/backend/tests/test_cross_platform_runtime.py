import builtins
from pathlib import Path

from backend.core import free_stack, platform_support
from backend.tools import browser_tools, desktop_tools, screen_tools, voice_tools
import backend.tools.finance_brain as finance_brain


def test_browser_tool_degrades_when_playwright_missing(monkeypatch) -> None:
    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("simulated missing playwright")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    result = browser_tools.read_url("https://example.com")
    assert result["title"] == "Browser unavailable"
    assert "Kattappa can still chat" in result["text"]


def test_screen_tool_degrades_when_capture_stack_missing(monkeypatch) -> None:
    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name in {"mss", "PIL"} or name.startswith("PIL."):
            raise ImportError("simulated missing screen stack")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    result = screen_tools.read_screen_snapshot()
    assert "Screen capture unavailable" in result["text"]
    assert result["words"] == []


def test_voice_tool_degrades_when_voice_stack_missing(monkeypatch) -> None:
    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name in {"pyttsx3", "faster_whisper"}:
            raise ImportError("simulated missing voice stack")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    monkeypatch.setattr(voice_tools.shutil, "which", lambda _name: None)
    assert "Speech output is unavailable" in voice_tools.speak("hello")
    assert "Speech-to-text is unavailable" in voice_tools.transcribe_file("missing.wav")


def test_kattappa_voice_profile_is_original() -> None:
    profile = voice_tools.voice_profile()
    assert profile["id"] == "kattappa_original_loyal_warrior"
    assert "deep" in profile["style"]
    assert profile["primary_spoken_language"] == "Telugu"
    assert profile["secondary_spoken_language"] == "English"
    assert profile["text_output_language"] == "English"
    assert "must not clone" in profile["policy"]
    assert "movie character" in profile["policy"]
    assert "identifiable person's voice" in profile["policy"]


def test_voice_pipeline_status_is_not_browser_primary() -> None:
    status = voice_tools.voice_pipeline_status()
    assert status["mode"] == "local_backend_voice_pipeline"
    assert status["browser_speech_primary"] is False
    assert status["wake"]["engine"] == "openwakeword"
    assert status["wake"]["primary_decision"] in {"openwakeword_custom_models", "local_stt_wake_name_parser"}
    assert status["stt"]["engine"] == "faster-whisper"
    assert status["tts"]["available"] in {True, False}


def test_free_stack_does_not_false_green_missing_optional_adapters(monkeypatch) -> None:
    monkeypatch.setattr(free_stack.importlib.util, "find_spec", lambda _name: None)
    monkeypatch.setattr(free_stack.shutil, "which", lambda _name: None)

    report = free_stack.free_stack_report()
    by_key = {item["key"]: item for item in report["capabilities"]}

    for key in ["playwright", "pytesseract", "faster_whisper", "openwakeword", "tesseract"]:
        assert by_key[key]["installed"] is False
        assert by_key[key]["actual_installed"] is False
        assert by_key[key]["status"] == "fallback"
        assert by_key[key]["usable"] is True

    assert report["ready_count"] < report["total_count"]
    assert report["fallback_count"] >= 5


def test_platform_support_reports_installed_vs_fallback_states(monkeypatch) -> None:
    monkeypatch.setattr(platform_support, "_module_available", lambda _name: False)
    monkeypatch.setattr(platform_support, "_tts_ready", lambda _system, _commands: False)
    monkeypatch.setattr(platform_support, "_external_projects_root", lambda _root: Path("Z:/definitely-missing-external-projects"))
    monkeypatch.setattr(
        platform_support,
        "_command_map",
        lambda: {
            "ollama": False,
            "npm": True,
            "node": True,
            "tesseract": False,
            "say": False,
            "spd-say": False,
            "espeak": False,
            "localsend": False,
            "localsend_app": False,
        },
    )

    report = platform_support.platform_support_report()
    features = {item["feature"]: item for item in report["features"]}

    for feature in ["browser_automation", "ocr", "speech_to_text", "wake_word", "kronos_finance"]:
        assert features[feature]["status"] == "fallback"
        assert features[feature]["installed"] is False
        assert features[feature]["usable"] is True


def test_kronos_status_uses_fallback_when_repository_is_absent(monkeypatch) -> None:
    monkeypatch.setattr(finance_brain, "KRONOS_ROOT", Path("Z:/definitely-missing-kronos"))
    status = finance_brain.kronos_status()
    assert status["installed"] is False
    assert status["status"] == "fallback"
    assert status["fallback_available"] is True
    assert status["fallback_engine"] == "kattappa-local-ohlcv-baseline"
    assert status["ready_for_real_kronos"] is False


def test_voice_wake_command_parser() -> None:
    parsed = voice_tools.parse_wake_command("Kattappa open settings")
    assert parsed["wake_detected"] is True
    assert parsed["wake_name"] == "kattappa"
    assert parsed["command"] == "open settings"

    no_wake = voice_tools.parse_wake_command("open settings")
    assert no_wake["wake_detected"] is False
    assert no_wake["command"] == ""


def test_desktop_launcher_uses_mac_shortcut(monkeypatch) -> None:
    events = []

    class FakePyAutoGui:
        FAILSAFE = False

        def hotkey(self, *keys):
            events.append(("hotkey", keys))

        def press(self, key):
            events.append(("press", key))

    monkeypatch.setattr(desktop_tools, "_ensure_enabled", lambda: None)
    monkeypatch.setattr(desktop_tools, "_pyautogui", lambda: FakePyAutoGui())
    monkeypatch.setattr(desktop_tools.platform, "system", lambda: "Darwin")

    assert desktop_tools.open_app_launcher() == "spotlight launcher opened"
    assert events == [("hotkey", ("command", "space"))]
