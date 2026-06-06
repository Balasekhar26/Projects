from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path


KATTAPPA_VOICE_PROFILE = {
    "id": "kattappa_original_loyal_warrior",
    "name": "Kattappa Original Loyal Warrior",
    "style": "deep, calm, authoritative, warm, and cinematic",
    "rate": 145,
    "volume": 0.95,
    "pitch": 42,
    "policy": (
        "Original assistant voice profile only. It must not clone, imitate, or claim to be "
        "any movie character, actor, or identifiable person's voice."
    ),
}


def speak(text: str) -> str:
    try:
        import pyttsx3
    except Exception as exc:
        return _speak_with_os_adapter(text, exc)
    try:
        engine = pyttsx3.init()
        _apply_kattappa_profile(engine)
        engine.say(text)
        engine.runAndWait()
        return "spoken via pyttsx3 using Kattappa original voice profile"
    except Exception as exc:
        return _speak_with_os_adapter(text, exc)


def voice_profile() -> dict[str, object]:
    return dict(KATTAPPA_VOICE_PROFILE)


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
        subprocess.Popen(["say", "-r", str(KATTAPPA_VOICE_PROFILE["rate"]), text])
        return "spoken via macOS say using Kattappa original voice profile"
    if system == "linux":
        if shutil.which("espeak"):
            subprocess.Popen(
                [
                    "espeak",
                    "-s",
                    str(KATTAPPA_VOICE_PROFILE["rate"]),
                    "-p",
                    str(KATTAPPA_VOICE_PROFILE["pitch"]),
                    text,
                ]
            )
            return "spoken via espeak using Kattappa original voice profile"
        if shutil.which("spd-say"):
            subprocess.Popen(["spd-say", "-r", "-25", text])
            return "spoken via spd-say using Kattappa original voice profile"
    if system == "windows" and shutil.which("powershell"):
        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$synth.Rate = -2; "
            "$synth.Volume = 95; "
            "$synth.Speak($args[0])"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", command, text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return "spoken via Windows speech using Kattappa original voice profile"
    return f"Speech output is unavailable on this OS/session: {cause}"


def _apply_kattappa_profile(engine: object) -> None:
    try:
        engine.setProperty("rate", KATTAPPA_VOICE_PROFILE["rate"])
        engine.setProperty("volume", KATTAPPA_VOICE_PROFILE["volume"])
    except Exception:
        return
    try:
        voices = engine.getProperty("voices") or []
    except Exception:
        return
    preferred_terms = ("male", "david", "mark", "ravi", "english", "india")
    for voice in voices:
        label = f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')}".lower()
        if any(term in label for term in preferred_terms):
            try:
                engine.setProperty("voice", voice.id)
            except Exception:
                pass
            break
