"""Barge-In Engine (Program 17.0).

Monages user interruption during active assistant text-to-speech output.
"""
from __future__ import annotations

import logging
import time

from backend.core.voice.runtime.voice_session import VoiceSession, VoiceState

logger = logging.getLogger(__name__)

BARGE_IN_SPEECH_FRAMES = 3
MIN_INTERRUPT_COOLDOWN_SECONDS = 0.25


class BargeInEngine:
    """Interruption controller that cancels active TTS playback when user speech is detected."""

    def __init__(self, session: VoiceSession) -> None:
        self.session = session
        self.consecutive_speech_chunks = 0
        self.last_interrupt_time = 0.0

    def process_barge_in(self, has_voice: bool) -> bool:
        """Process VAD speech frame and returns True if barge-in was triggered."""
        if not self.session.is_tts_playing:
            self.consecutive_speech_chunks = 0
            return False

        now = time.monotonic()
        if now - self.last_interrupt_time < MIN_INTERRUPT_COOLDOWN_SECONDS:
            return False

        if has_voice:
            self.consecutive_speech_chunks += 1
            if self.consecutive_speech_chunks >= BARGE_IN_SPEECH_FRAMES:
                logger.info(
                    "Barge-in triggered: user voice detected during playback in session %s",
                    self.session.session_id,
                )
                self.session.interrupted = True
                self.session.is_tts_playing = False
                self.consecutive_speech_chunks = 0
                self.last_interrupt_time = now

                # Invalidate temporary task approvals on interrupt (Rule 11 compliance)
                try:
                    from backend.agents.voice_agent import _get_or_create_session
                    va_session = _get_or_create_session(self.session.session_id)
                    if va_session and va_session.paused_task:
                        va_session.paused_task_approval_valid = False
                        logger.info("Barge-in: approval invalidated for paused task")
                except Exception:
                    pass

                return True
        else:
            self.consecutive_speech_chunks = max(0, self.consecutive_speech_chunks - 1)

        return False
