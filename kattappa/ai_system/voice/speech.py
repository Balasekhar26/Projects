from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.tools.voice_tools import voice_profile


@dataclass
class VoiceIO:
    whisper_model_size: str = "small"

    def speak(self, text: str) -> None:
        profile = voice_profile()
        try:
            import pyttsx3
        except Exception as exc:
            print(f"Speech output is unavailable on this OS/session: {exc}")
            return
        engine = pyttsx3.init()
        engine.setProperty("rate", profile["rate"])
        engine.setProperty("volume", profile["volume"])
        engine.say(text)
        engine.runAndWait()

    def transcribe_file(self, audio_path: Path) -> str:
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            return f"Speech-to-text is unavailable on this OS/session: {exc}"
        model = WhisperModel(self.whisper_model_size, device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(audio_path))
        return " ".join(segment.text.strip() for segment in segments).strip()
