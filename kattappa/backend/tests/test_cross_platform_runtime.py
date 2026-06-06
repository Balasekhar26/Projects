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
