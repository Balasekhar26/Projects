"""Unit tests for Program 31.0: Advanced Voice Runtime.

Verifies VAD threshold adaptation, Jitter Buffer re-ordering,
Emotion TTS tag extraction, and Telugu phonetic word normalizations.
"""
from __future__ import annotations

import pytest

from backend.core.voice.runtime.vad import VAD
from backend.core.voice.runtime.jitter_buffer import JitterBuffer
from backend.core.voice.runtime.emotion_tts import EmotionTTSManager
from backend.core.voice.runtime.telugu_helper import TeluguVoiceHelper


# ── VAD Tests ─────────────────────────────────────────────────────────────────

class TestVADAdaptation:
    def test_vad_noise_adaptation(self):
        # Multiplier of 1.5, EMA alpha = 0.5 for fast tests
        vad = VAD(alpha=0.5, noise_multiplier=1.5)
        initial_threshold = vad.current_threshold
        
        # Simulate constant quiet background noise chunk (16-bit PCM silent frames)
        # We write high-energy quiet bytes that don't trigger voice
        quiet_chunk = b"\x05\x00" * 100  # small quiet samples
        
        # Process silent frames to update background noise floor
        for _ in range(5):
            res = vad.process_chunk(quiet_chunk)
            assert res["has_voice"] is False
            
        # Background noise should shift, and current_threshold should update
        final_threshold = vad.current_threshold
        assert final_threshold != initial_threshold


# ── Jitter Buffer Tests ────────────────────────────────────────────────────────

class TestJitterBuffer:
    def test_jitter_buffer_reordering(self):
        jb = JitterBuffer(target_delay_packets=3)
        
        # Push out-of-order packets
        jb.push(2, b"Packet 2")
        jb.push(1, b"Packet 1")
        
        # Pop returns None because buffer size (2) is below target_delay (3)
        assert jb.pop() is None
        
        # Push 3rd packet
        jb.push(3, b"Packet 3")
        assert jb.size == 3
        
        # Should pop sequence 1 (lowest sequence number first)
        assert jb.pop() == b"Packet 1"
        assert jb.pop(force=True) == b"Packet 2"
        assert jb.pop(force=True) == b"Packet 3"

    def test_jitter_buffer_duplicates(self):
        jb = JitterBuffer(target_delay_packets=2)
        jb.push(1, b"A")
        jb.push(1, b"A")  # duplicate should be ignored
        jb.push(2, b"B")

        assert jb.size == 2
        assert jb.pop() == b"A"
        assert jb.pop(force=True) == b"B"

    def test_discard_late_packets(self):
        jb = JitterBuffer(target_delay_packets=1)
        jb.push(2, b"B")
        
        # Pop sequence 2
        assert jb.pop() == b"B"
        
        # Sequence 1 arrives late (after we already popped 2)
        jb.push(1, b"A")
        # Late packet should be discarded to avoid rewinding streams
        assert jb.size == 0


# ── Emotion TTS Tests ──────────────────────────────────────────────────────────

class TestEmotionTTS:
    def test_extract_explicit_tag(self):
        text = "[SAD] I failed to complete the task."
        clean_text, emotion = EmotionTTSManager.extract_emotion_tag(text)
        
        assert clean_text == "I failed to complete the task."
        assert emotion == "SAD"
        
        params = EmotionTTSManager.get_speech_parameters(emotion)
        assert params["length_scale"] == 1.25  # slower rate

    def test_extract_implicit_keyword(self):
        text = "Wow, that is amazing news!"
        clean_text, emotion = EmotionTTSManager.extract_emotion_tag(text)
        
        assert clean_text == text
        assert emotion == "SURPRISED"
        
        params = EmotionTTSManager.get_speech_parameters(emotion)
        assert params["length_scale"] == 0.90  # faster rate

    def test_unknown_tag_fallback(self):
        text = "[EXCITED] Let's go!"
        clean_text, emotion = EmotionTTSManager.extract_emotion_tag(text)
        
        # [EXCITED] is not registered -> falls back to NEUTRAL
        assert emotion == "NEUTRAL"


# ── Telugu Helper Tests ────────────────────────────────────────────────────────

class TestTeluguHelper:
    def test_digit_translation(self):
        text = "Room 304"
        phonetic = TeluguVoiceHelper.normalize_text(text)
        
        # Digits 3, 0, 4 translated to Telugu phonetic words
        assert "మూడు" in phonetic
        assert "సున్నా" in phonetic
        assert "నాలుగు" in phonetic

    def test_pause_punctuation_normalization(self):
        text = "Preparing... done."
        normalized = TeluguVoiceHelper.normalize_text(text)
        
        assert " -- " in normalized
