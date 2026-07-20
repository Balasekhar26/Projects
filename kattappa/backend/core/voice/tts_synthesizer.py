import time
import threading

class TTSSynthesizer:
    def __init__(self, voice_model: str = "te_IN-piper"):
        self.voice_model = voice_model
        self.is_speaking = False
        self.is_interrupted = False
        self._lock = threading.Lock()

    def speak(self, text: str) -> None:
        """Synthesizes and plays back speech in an interruptible background thread."""
        with self._lock:
            self.is_speaking = True
            self.is_interrupted = False
            
        # Simulates synthesis/playback with regular interruption checks
        words = text.split()
        for word in words:
            with self._lock:
                if self.is_interrupted:
                    break
            # Mock delay mimicking vocal duration per word
            time.sleep(0.2)
            
        with self._lock:
            self.is_speaking = False

    def interrupt(self) -> None:
        """Halts active audio playback immediately."""
        with self._lock:
            if self.is_speaking:
                self.is_interrupted = True
                self.is_speaking = False
