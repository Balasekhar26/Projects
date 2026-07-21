"""Voice Activity Detection (Program 17.0).

Handles high-frequency energy detection, turn boundaries, and VAD states.
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

# Constants
VAD_ENERGY_THRESHOLD = 0.005
SPEECH_START_FRAMES = 2          # 2 frames * ~30ms = ~60ms (<100ms target)
SPEECH_END_FRAMES = 15           # 15 frames * ~30ms = ~450ms (<500ms target)


class VAD:
    """Computes RMS energy and tracks sliding speech state to decide turn boundaries."""

    def __init__(self, alpha: float = 0.05, noise_multiplier: float = 1.5) -> None:
        self.consecutive_active_frames = 0
        self.consecutive_silent_frames = 0
        self.is_speaking = False
        self.background_noise = VAD_ENERGY_THRESHOLD
        self.alpha = alpha
        self.noise_multiplier = noise_multiplier

    @property
    def current_threshold(self) -> float:
        return max(VAD_ENERGY_THRESHOLD, self.background_noise * self.noise_multiplier)

    @staticmethod
    def calculate_rms(chunk: bytes) -> float:
        """Calculate Root Mean Square (RMS) energy of 16-bit mono PCM audio chunk."""
        if not chunk:
            return 0.0
        try:
            import numpy as np
            data = np.frombuffer(chunk, dtype=np.int16)
            if len(data) == 0:
                return 0.0
            normalized = data.astype(float) / 32768.0
            return float(np.sqrt(np.mean(normalized ** 2)))
        except Exception:
            # Fallback simple python loop
            samples = []
            for i in range(0, len(chunk), 2):
                if i + 1 < len(chunk):
                    val = int.from_bytes(chunk[i:i+2], byteorder="little", signed=True)
                    samples.append(val / 32768.0)
            if not samples:
                return 0.0
            return float(math.sqrt(sum(s**2 for s in samples) / len(samples)))

    def process_chunk(self, chunk: bytes) -> dict[str, Any]:
        """Scans raw audio chunk and returns event transitions.

        Possible event statuses in dict:
            - "silence"
            - "speech_start"
            - "speech"
            - "speech_end"
        """
        rms = self.calculate_rms(chunk)
        threshold = self.current_threshold
        has_voice = rms > threshold

        # Update background noise estimate during silences
        if not self.is_speaking and not has_voice:
            self.background_noise = self.alpha * rms + (1 - self.alpha) * self.background_noise

        result = {
            "rms": rms,
            "has_voice": has_voice,
            "event": "silence"
        }

        if has_voice:
            self.consecutive_silent_frames = 0
            if not self.is_speaking:
                self.consecutive_active_frames += 1
                if self.consecutive_active_frames >= SPEECH_START_FRAMES:
                    self.is_speaking = True
                    result["event"] = "speech_start"
                    logger.debug("VAD: Speech start detected")
            else:
                result["event"] = "speech"
        else:
            self.consecutive_active_frames = 0
            if self.is_speaking:
                self.consecutive_silent_frames += 1
                if self.consecutive_silent_frames >= SPEECH_END_FRAMES:
                    self.is_speaking = False
                    self.consecutive_silent_frames = 0
                    result["event"] = "speech_end"
                    logger.debug("VAD: Speech end detected")
                else:
                    result["event"] = "speech"

        return result
