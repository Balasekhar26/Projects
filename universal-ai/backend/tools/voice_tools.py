from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path


def speak(text: str) -> str:
    try:
        import pyttsx3
    except Exception as exc:
        return _speak_with_os_adapter(text, exc)
    try:
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        return "spoken via pyttsx3"
    except Exception as exc:
        return _speak_with_os_adapter(text, exc)


def transcribe_file(path: str, model_size: str = "small") -> str:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        return f"Speech-to-text is unavailable on this OS/session: {exc}"
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(Path(path)))
    return " ".join(segment.text.strip() for segment in segments).strip()


def _speak_with_os_adapter(text: str, cause: Exception) -> str:
    system = platform.system().lower()
    if system == "darwin" and shutil.which("say"):
        subprocess.Popen(["say", text])
        return "spoken via macOS say"
    if system == "linux":
        for command in ("spd-say", "espeak"):
            if shutil.which(command):
                subprocess.Popen([command, text])
                return f"spoken via {command}"
    if system == "windows" and shutil.which("powershell"):
        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$synth.Speak($args[0])"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", command, text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return "spoken via Windows speech"
    return f"Speech output is unavailable on this OS/session: {cause}"
