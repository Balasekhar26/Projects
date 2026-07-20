import os
import json
import threading
import time
from backend.core.voice.audio_capture import AudioCapture
from backend.core.voice.vad_detector import VADDetector
from backend.core.voice.wake_word import WakeWordEngine
from backend.core.voice.stt_streamer import STTStreamer
from backend.core.voice.tts_synthesizer import TTSSynthesizer
from backend.core.voice.dialogue_manager import DialogueManager
from backend.core.voice.conversation_state import ConversationStateManager

class VoiceEngine:
    def __init__(self):
        self.capture = AudioCapture()
        self.vad = VADDetector()
        self.wake = WakeWordEngine()
        self.stt = STTStreamer()
        self.tts = TTSSynthesizer()
        self.dialogue = DialogueManager()
        self.state = ConversationStateManager()
        self.is_running = False
        self._thread = None
        self.profile = self._load_profile()

    def _load_profile(self) -> dict:
        """Loads voice personality configurations from voice_profiles.json."""
        config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "voice_profiles.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("default", {})
            except Exception:
                pass
        return {
            "language": "te",
            "voice": "te_IN-female-medium",
            "speed": 1.0,
            "pitch": 1.0,
            "noise_scale": 0.55,
            "length_scale": 1.00,
            "noise_w": 0.75
        }

    def start(self) -> None:
        """Starts background streaming audio handlers."""
        self.is_running = True
        self.capture.start_capture()
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stops background audio capture and processing workers."""
        self.is_running = False
        self.capture.stop_capture()
        if self._thread:
            self._thread.join(timeout=1.0)
        self.tts.interrupt()
        self.state.reset()

    def _process_loop(self) -> None:
        """Continuously pulls raw frames, runs VAD checks, interrupts TTS on speech, and routes STT texts."""
        while self.is_running:
            # Buffer Overflow Recovery: drop oldest frames if queue gets backed up
            if self.capture.frame_queue.qsize() > 80:
                while self.capture.frame_queue.qsize() > 10:
                    try:
                        self.capture.frame_queue.get_nowait()
                    except Exception:
                        break
                        
            frame = self.capture.get_next_frame(timeout=0.2)
            if frame is None:
                continue
                
            is_speech_active = self.vad.is_speech(frame)
            
            if is_speech_active:
                self.state.active_speaker_state = "LISTENING"
                self.state.turn_ownership = "USER"
                
                # TTS Interruption: immediately stop speech output if user speaks
                if self.tts.is_speaking:
                    self.tts.interrupt()
                    self.state.is_interrupted = True
                    
                transcript = self.stt.append_audio(frame)
                if transcript:
                    # Merge transcript windows dynamically
                    self.state.partial_transcript = self.state.merge_transcripts(
                        self.state.partial_transcript, 
                        transcript
                    )
                    
                    response_text = self.dialogue.process_input(self.state.partial_transcript)
                    self.state.active_speaker_state = "SPEAKING"
                    self.state.turn_ownership = "ASSISTANT"
                    
                    threading.Thread(
                        target=self.tts.speak, 
                        args=(response_text,), 
                        daemon=True
                    ).start()
            else:
                self.stt.append_audio(frame)
                if not self.tts.is_speaking and self.state.active_speaker_state == "SPEAKING":
                    self.state.active_speaker_state = "IDLE"
                    self.state.turn_ownership = "USER"
