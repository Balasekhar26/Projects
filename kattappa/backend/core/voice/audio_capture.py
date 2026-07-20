import queue
import threading
import time
import numpy as np

class AudioCapture:
    def __init__(self, sample_rate: int = 16000, frame_duration_ms: int = 20):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.samples_per_frame = int(sample_rate * (frame_duration_ms / 1000.0))
        self.frame_queue = queue.Queue(maxsize=100)
        self.is_capturing = False
        self._thread = None

    def start_capture(self) -> None:
        """Starts capturing audio frames in a background thread."""
        self.is_capturing = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop_capture(self) -> None:
        """Stops active capture thread."""
        self.is_capturing = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def get_next_frame(self, timeout: float = 1.0) -> np.ndarray | None:
        """Fetches the next audio frame from the queue."""
        try:
            return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _capture_loop(self) -> None:
        """Simulates microphone capture loop of mono int16 audio frames."""
        while self.is_capturing:
            # Generate mock mono frame (silence/noise) for testing/headless execution
            mock_frame = np.zeros(self.samples_per_frame, dtype=np.int16)
            try:
                self.frame_queue.put(mock_frame, block=False)
            except queue.Full:
                pass
            time.sleep(self.frame_duration_ms / 1000.0)
