import numpy as np

class VADDetector:
    def __init__(self, energy_threshold: float = 500.0):
        self.energy_threshold = energy_threshold

    def is_speech(self, frame: np.ndarray) -> bool:
        """Determines if the given audio frame contains speech based on Root Mean Square (RMS) energy."""
        if len(frame) == 0:
            return False
            
        # Compute RMS energy of the audio frame
        rms = np.sqrt(np.mean(frame.astype(np.float64) ** 2))
        return rms > self.energy_threshold
