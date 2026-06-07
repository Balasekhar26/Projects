import builtins

from backend.tools import browser_tools, desktop_tools, screen_tools, voice_tools


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
