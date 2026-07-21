"""Streaming STT (Program 17.0).

Handles segment-by-segment low-latency audio transcription and confidence gating.
"""
from __future__ import annotations

import os
import tempfile
import time
import wave
from typing import Any, Dict

from backend.agents.voice_agent import transcribe_audio


class StreamingSTT:
    """Invokes Whisper transcription on speech segments and monitors confidence ceilings."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def transcribe_segment(pcm_data: bytes) -> Dict[str, Any]:
        """Transcribe a segment of raw 16kHz mono PCM bytes.

        Returns transcription result dictionary with keys:
            - "ok": bool
            - "transcript": str
            - "confidence": float
            - "language": str
            - "reason": str (if failed)
        """
        if not pcm_data:
            return {
                "ok": False,
                "transcript": "",
                "confidence": 0.0,
                "language": "unknown",
                "reason": "empty_audio_data"
            }

        # Write PCM data to temp WAV file for Whisper consumption
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name
        try:
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm_data)

            # Transcribe audio using safety-gated wrapper
            result = transcribe_audio(wav_path)
            return result
        finally:
            try:
                os.unlink(wav_path)
            except Exception:
                pass
