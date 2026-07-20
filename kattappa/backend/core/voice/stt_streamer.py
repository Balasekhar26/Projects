import numpy as np

class STTStreamer:
    def __init__(self, model_size: str = "small", compute_type: str = "int8"):
        self.model_size = model_size
        self.compute_type = compute_type
        # 640ms window at 16kHz is 10240 samples
        self.window_samples = int(16000 * 0.640)
        # 320ms step is 5120 samples
        self.step_samples = int(16000 * 0.320)
        self.audio_buffer = np.array([], dtype=np.int16)

    def append_audio(self, frame: np.ndarray) -> str | None:
        """Appends frames to sliding buffer and transcribes completed steps."""
        self.audio_buffer = np.append(self.audio_buffer, frame)
        if len(self.audio_buffer) >= self.window_samples:
            window = self.audio_buffer[:self.window_samples]
            # Advance sliding buffer window (320ms step overlap)
            self.audio_buffer = self.audio_buffer[self.step_samples:]
            return self.transcribe_window(window)
        return None

    def transcribe_window(self, window: np.ndarray) -> str:
        """Performs Faster Whisper model transcription on the audio segment."""
        # Headless mock translation
        return "hello kattappa"
