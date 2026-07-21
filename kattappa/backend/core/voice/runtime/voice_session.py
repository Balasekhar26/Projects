"""Voice Session (Program 17.0).

Manages connection state, audio buffers, input/output constraints, and active TTS flags.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional


class VoiceState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"


class VoiceSession:
    """Manages raw audio buffers and connection states for a duplex voice stream.

    Enforces buffer safety boundaries:
      - MAX_INPUT_BUFFER = 5 seconds of 16kHz 16-bit PCM (160,000 bytes)
      - MAX_OUTPUT_BUFFER = 10 MB limit for safety
    """

    MAX_INPUT_BUFFER = 5 * 32000  # 5 seconds of 16kHz 16-bit PCM mono
    MAX_OUTPUT_BUFFER = 10 * 1024 * 1024  # 10 MB

    def __init__(self, session_id: Optional[str] = None, voice_profile: str = "kattappa") -> None:
        self.session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        self.voice_profile = voice_profile
        self.state = VoiceState.IDLE
        self.created_at = time.time()
        self.last_activity = time.time()

        # Buffers
        self._input_buffer = bytearray()
        self.output_buffer_size = 0

        # State flags
        self.is_tts_playing = False
        self.interrupted = False
        self.active_checkpoint_id = ""

    def append_input_audio(self, chunk: bytes) -> None:
        """Appends bytes to the input buffer, discarding oldest frames if overflow occurs."""
        self._input_buffer.extend(chunk)
        self.last_activity = time.time()

        # Enforce buffer limit (Rule: MAX_INPUT_BUFFER = 5 seconds)
        if len(self._input_buffer) > self.MAX_INPUT_BUFFER:
            excess = len(self._input_buffer) - self.MAX_INPUT_BUFFER
            del self._input_buffer[:excess]

    def get_input_buffer(self) -> bytes:
        """Get copy of the input audio bytes."""
        return bytes(self._input_buffer)

    def clear_input_buffer(self) -> None:
        """Clear the input audio buffer."""
        self._input_buffer.clear()

    def update_activity(self) -> None:
        self.last_activity = time.time()
