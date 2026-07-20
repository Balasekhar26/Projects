import pytest
import time
import numpy as np
from backend.core.voice.audio_capture import AudioCapture
from backend.core.voice.vad_detector import VADDetector
from backend.core.voice.tts_synthesizer import TTSSynthesizer
from backend.core.voice.voice_engine import VoiceEngine

def test_audio_capture_queuing() -> None:
    capture = AudioCapture(frame_duration_ms=10)
    capture.start_capture()
    # Let buffer capture a few frames
    time.sleep(0.05)
    
    frame = capture.get_next_frame(timeout=0.1)
    assert frame is not None
    assert len(frame) == capture.samples_per_frame
    capture.stop_capture()

def test_vad_energy_detector() -> None:
    vad = VADDetector(energy_threshold=100.0)
    
    # Silence frame (all zeroes)
    silence = np.zeros(320, dtype=np.int16)
    assert not vad.is_speech(silence)
    
    # Loud speech frame (simulated square wave)
    speech = np.full(320, 1000, dtype=np.int16)
    assert vad.is_speech(speech)

def test_tts_synthesizer_interruption() -> None:
    tts = TTSSynthesizer()
    
    # Start speak synthesis loop in thread
    thread = tts.speak("hello world this is a test speech to interrupt")
    # Simulate playback trigger
    import threading
    t = threading.Thread(target=tts.speak, args=("hello world this is a test",))
    t.start()
    
    # Small sleep to let speech start
    time.sleep(0.05)
    assert tts.is_speaking
    
    # Interrupt active playback
    tts.interrupt()
    time.sleep(0.1)
    assert not tts.is_speaking
    assert tts.is_interrupted

def test_voice_engine_interruption_integration() -> None:
    engine = VoiceEngine()
    engine.start()
    
    # Simulate active TTS playback
    engine.tts.is_speaking = True
    assert engine.tts.is_speaking
    
    # Feed active speech frame directly into engine process loop
    loud_frame = np.full(engine.capture.samples_per_frame, 1500, dtype=np.int16)
    engine.capture.frame_queue.put(loud_frame)
    
    # Process loop should detect speech and interrupt active playback
    time.sleep(0.3)
    assert not engine.tts.is_speaking
    assert engine.tts.is_interrupted
    engine.stop()

def test_conversation_state_manager_merges() -> None:
    from backend.core.voice.conversation_state import ConversationStateManager
    manager = ConversationStateManager()
    
    # 1. Overlapping text window merge
    merged1 = manager.merge_transcripts("turn on the", "the bedroom lights")
    assert merged1 == "turn on the bedroom lights"
    
    # 2. Non-overlapping text window merge
    merged2 = manager.merge_transcripts("turn on the lights", "actually make them blue")
    assert merged2 == "turn on the lights actually make them blue"
    
    # 3. Empty input boundary merge
    assert manager.merge_transcripts("", "hello") == "hello"

def test_voice_engine_profile_loading() -> None:
    engine = VoiceEngine()
    profile = engine.profile
    assert profile is not None
    assert profile.get("language") == "te"
    assert "voice" in profile

def test_buffer_overflow_recovery() -> None:
    engine = VoiceEngine()
    # Fill frame queue up to trigger overflow thresholds
    for _ in range(90):
        engine.capture.frame_queue.put(np.zeros(320, dtype=np.int16))
    
    # Assert queue size is initially overflowed
    assert engine.capture.frame_queue.qsize() > 80
    
    # Initiate process loop step
    engine.start()
    time.sleep(0.3)
    # Check that buffer was successfully flushed/drained to keep real-time latency
    assert engine.capture.frame_queue.qsize() <= 10
    engine.stop()
