"""Streaming TTS (Program 17.0).

Handles sentence-level incremental text-to-speech rendering and streaming bytes.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator

from backend.tools.voice_tools import _piper_voice_model, _piper_process_env, EMOTION_PROFILES
from backend.core.voice.runtime.voice_session import VoiceSession


class StreamingTTS:
    """Incremental sentence-by-sentence text synthesizer."""

    def __init__(self, voice_session: VoiceSession) -> None:
        self.session = voice_session

    @staticmethod
    def split_sentences(text: str) -> list[str]:
        """Split a block of text into sentences or major clauses."""
        pattern = re.compile(r'(?<!\b(?:Mr|Ms|Dr|eg|ie|vs)\.)(?<=[.!?])\s+|(?<=\n)\s*')
        sentences = [s.strip() for s in pattern.split(text) if s.strip()]
        return sentences

    def generate_speech_stream(self, text: str, emotion: str = "NEUTRAL") -> Iterator[bytes]:
        """Iterates over sentences, synthesizes, and yields raw 16kHz PCM audio bytes."""
        sentences = self.split_sentences(text)
        params = EMOTION_PROFILES.get(emotion, EMOTION_PROFILES["NEUTRAL"])
        speed = params.get("speed", 1.0)
        piper_model_path = _piper_voice_model()

        for sentence in sentences:
            # Check for interrupt before starting sentence synthesis
            if self.session.interrupted:
                break

            if piper_model_path and shutil.which("piper"):
                pcm_stream = self._stream_piper(sentence, piper_model_path, speed)
            else:
                pcm_stream = self._stream_fallback(sentence, speed)

            for chunk in pcm_stream:
                if self.session.interrupted:
                    break
                yield chunk

    def _stream_piper(self, text: str, model_path: Path, speed: float) -> Iterator[bytes]:
        """Streams raw PCM bytes from local Piper command subprocess."""
        length_scale = 1.0 / speed if speed != 1.0 else 1.0
        piper_command = shutil.which("piper")
        if not piper_command:
            return
        env = _piper_process_env()

        proc = subprocess.Popen(
            [
                piper_command,
                "--model", str(model_path),
                "--output-raw",
                "--length_scale", str(length_scale)
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        try:
            proc.stdin.write(text.encode("utf-8"))
            proc.stdin.close()
            while True:
                if self.session.interrupted:
                    break
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                yield chunk
        except Exception:
            pass
        finally:
            try:
                proc.terminate()
            except Exception:
                pass

    def _stream_fallback(self, text: str, speed: float) -> Iterator[bytes]:
        """Streams PCM bytes from fallback engine by saving WAV and skipping headers."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            rate = int(200 * speed)
            engine.setProperty("rate", rate)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                temp_path = tf.name
            try:
                engine.save_to_file(text, temp_path)
                engine.runAndWait()

                if Path(temp_path).exists() and Path(temp_path).stat().st_size > 44:
                    with open(temp_path, "rb") as f:
                        f.seek(44)  # Skip 44-byte WAV header for raw PCM mono 16-bit
                        while True:
                            if self.session.interrupted:
                                break
                            chunk = f.read(4096)
                            if not chunk:
                                break
                            yield chunk
            finally:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception:
            pass

