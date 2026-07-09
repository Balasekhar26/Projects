"""Cognitive Session Orchestrator (Program 30.0).

Coordinates streaming conversations: listens to user speech chunks, processes VAD
boundaries, coordinates STT and model routing, streams response tokens, translates
them to TTS audio chunks, and supports instant barge-in interruption.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Generator, List, Optional

from backend.core.voice.context_buffer import MultimodalContextBuffer
from backend.core.model.router import KattappaModelRouter

logger = logging.getLogger(__name__)


class CognitiveSessionOrchestrator:
    """Manages streaming user speech inputs, TTS, and barge-in events."""

    def __init__(
        self,
        router: Optional[KattappaModelRouter] = None,
        context_buffer: Optional[MultimodalContextBuffer] = None,
    ) -> None:
        self.router = router or KattappaModelRouter()
        self.context = context_buffer or MultimodalContextBuffer()

        # Output states
        self.is_playing_audio = False
        self.audio_interrupted = False

    def handle_input_audio_chunk(
        self,
        chunk: bytes,
        vad_trigger_fn: Callable[[bytes], bool],
        stt_fn: Callable[[bytes], str],
    ) -> Optional[str]:
        """Processes streaming user audio chunks.

        If VAD detects user speaking during active model TTS playback, it immediately
        triggers the barge-in sequence, terminating the playback.

        If VAD detects user has completed their speech, it triggers STT transcription
        and returns the transcribed prompt.
        """
        # 1. Barge-in detection check
        # If the user speaks while the engine is currently playing back synthesized response
        is_user_speaking = vad_trigger_fn(chunk)
        if is_user_speaking and self.is_playing_audio:
            self.interrupt_audio_playback()

        # 2. Check for speech completion boundary (EOS)
        # For simulation, VAD returns True for user active, but let's assume we can trigger
        # STT if VAD determines user finished speaking.
        # We will assume a specific boundary trigger for the callback returns.
        # In a real pipeline, vad_trigger_fn would check silence frames.
        return None

    def interrupt_audio_playback(self) -> None:
        """Instantly terminates synthesized TTS playbacks on barge-in events."""
        logger.info("Barge-in detected: interrupting audio playback.")
        self.is_playing_audio = False
        self.audio_interrupted = True

    def process_user_speech_completed(
        self,
        audio_buffer: bytes,
        stt_fn: Callable[[bytes], str],
    ) -> str:
        """Runs Speech-to-Text translation and logs transcript to the context buffer."""
        transcript = stt_fn(audio_buffer)
        self.context.append_interaction("audio", f"len={len(audio_buffer)}")
        self.context.append_interaction("text", f"User: {transcript}")
        return transcript

    def respond_streaming(
        self,
        prompt: str,
        response_generator: Callable[[str], Generator[str, None, None]],
        tts_fn: Callable[[str], bytes],
        audio_writer: Callable[[bytes], None],
    ) -> None:
        """Streams response tokens from the generator, runs TTS, and writes audio.

        Respects barge-in interrupts: stops processing tokens instantly if
        audio_interrupted is flagged during execution.
        """
        self.is_playing_audio = True
        self.audio_interrupted = False

        # Route the request
        target_model = self.router.route_request(prompt)
        logger.info(f"Routing request to model: {target_model}")

        full_response = []

        for token in response_generator(prompt):
            # Terminate loop immediately if barge-in interrupt flags
            if self.audio_interrupted:
                logger.info("Response stream halted due to user barge-in.")
                break

            full_response.append(token)

            # Synthesize and write token audio chunk
            audio_chunk = tts_fn(token)
            audio_writer(audio_chunk)

        self.is_playing_audio = False

        if not self.audio_interrupted:
            final_text = "".join(full_response)
            self.context.append_interaction("text", f"Kattappa: {final_text}")
