"""Unit tests for Program 17.0 Streaming Voice Runtime Hardening.

Covers VAD, Barge-In, VoiceSession buffers, Streaming STT/TTS modules, and WebSocket handlers.
"""
from __future__ import annotations

import math
import time
import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from backend.main import app
from backend.core.voice.runtime.voice_session import VoiceSession, VoiceState
from backend.core.voice.runtime.vad import VAD
from backend.core.voice.runtime.barge_in import BargeInEngine
from backend.core.voice.runtime.streaming_tts import StreamingTTS
from backend.core.voice.runtime.streaming_stt import StreamingSTT
from backend.core.voice.runtime.latency_metrics import LatencyMetrics


# ── 1. VoiceSession Buffer Boundaries ────────────────────────────────────────

class TestVoiceSessionHardening:
    def test_session_init_defaults(self):
        sess = VoiceSession(session_id="sess-hard-01")
        assert sess.session_id == "sess-hard-01"
        assert sess.state == VoiceState.IDLE
        assert sess.is_tts_playing is False
        assert sess.interrupted is False

    def test_input_buffer_overflow_protection(self):
        sess = VoiceSession(session_id="sess-overflow")
        # Write more than 5 seconds of 16kHz PCM (160,000 bytes)
        excess_chunk = b"\x01" * (VoiceSession.MAX_INPUT_BUFFER + 5000)
        sess.append_input_audio(excess_chunk)
        
        # Buffer must be strictly capped at MAX_INPUT_BUFFER
        buf = sess.get_input_buffer()
        assert len(buf) == VoiceSession.MAX_INPUT_BUFFER
        assert buf == excess_chunk[5000:]  # oldest frames discarded


# ── 2. VAD High Frequency Turn Detection ──────────────────────────────────────

class TestVADHardening:
    def test_vad_consecutive_active_frames(self):
        vad = VAD()
        # Sine wave active chunk
        active_pcm = bytes()
        for i in range(160):
            v = int(12000 * math.sin(2 * math.pi * 440 * i / 16000))
            data = v.to_bytes(2, "little", signed=True)
            active_pcm += data

        # 1st active frame
        res1 = vad.process_chunk(active_pcm)
        assert res1["event"] == "silence"  # Requires 2 frames for start
        assert vad.is_speaking is False

        # 2nd active frame -> Speech start
        res2 = vad.process_chunk(active_pcm)
        assert res2["event"] == "speech_start"
        assert vad.is_speaking is True

    def test_vad_silence_timeout_boundary(self):
        vad = VAD()
        vad.is_speaking = True

        silent_pcm = b"\x00\x00" * 160
        # Process 14 silent frames (less than SPEECH_END_FRAMES = 15)
        for _ in range(14):
            res = vad.process_chunk(silent_pcm)
            assert res["event"] == "speech"
            assert vad.is_speaking is True

        # 15th silent frame -> Speech end
        res_end = vad.process_chunk(silent_pcm)
        assert res_end["event"] == "speech_end"
        assert vad.is_speaking is False


# ── 3. Barge-In Interruption ──────────────────────────────────────────────────

class TestBargeInHardening:
    def test_barge_in_gated_by_cooldown(self):
        sess = VoiceSession("sess-barge")
        sess.is_tts_playing = True
        engine = BargeInEngine(sess)

        # Triggers speech frames
        assert engine.process_barge_in(has_voice=True) is False  # 1st frame
        assert engine.process_barge_in(has_voice=True) is False  # 2nd frame
        assert engine.process_barge_in(has_voice=True) is True   # 3rd frame -> barge-in

        # Set TTS playing back to True
        sess.is_tts_playing = True
        sess.interrupted = False
        # Cooldown prevents immediate re-interrupt within 250ms
        assert engine.process_barge_in(has_voice=True) is False


# ── 4. Streaming TTS Sentence Splitting ──────────────────────────────────────

class TestStreamingTTSHardening:
    def test_tts_generator_splits_sentences(self):
        sess = VoiceSession("sess-tts")
        tts = StreamingTTS(sess)
        text = "Hello my lord! Kattappa is online. I can assist you."
        sentences = tts.split_sentences(text)
        assert len(sentences) == 3
        assert sentences[0] == "Hello my lord!"
        assert sentences[1] == "Kattappa is online."

    def test_tts_stream_stops_on_interrupt(self):
        sess = VoiceSession("sess-tts-interrupt")
        tts = StreamingTTS(sess)
        
        # Mock speak outputs
        mock_pcm = [b"\x01\x02", b"\x03\x04"]
        with patch.object(tts, "_stream_fallback", return_value=mock_pcm):
            # Start streaming response
            stream = tts.generate_speech_stream("Sentence one. Sentence two.")
            
            # Consume 1st chunk
            chunk1 = next(stream)
            assert chunk1 == b"\x01\x02"

            # Simulate barge-in interrupt
            sess.interrupted = True

            # Iteration should terminate immediately
            with pytest.raises(StopIteration):
                next(stream)


# ── 5. Latency Telemetry ─────────────────────────────────────────────────────

class TestLatencyMetricsHardening:
    def test_telemetry_calculations(self):
        telemetry = LatencyMetrics("sess-telemetry")
        telemetry.mark_turn_start()
        time.sleep(0.01)
        telemetry.mark_stt_start()
        time.sleep(0.01)
        telemetry.mark_stt_end()
        telemetry.mark_planning_start()
        time.sleep(0.01)
        telemetry.mark_planning_end()
        telemetry.mark_tts_start()
        time.sleep(0.01)
        telemetry.mark_tts_first_chunk()

        metrics = telemetry.get_metrics_dict()
        assert metrics["stt_latency_ms"] > 0
        assert metrics["planning_latency_ms"] > 0
        assert metrics["tts_start_latency_ms"] > 0
        assert metrics["end_to_end_latency_ms"] > 0


# ── 6. WebSocket Protocol & Handshake ─────────────────────────────────────────

class TestWebSocketProtocolHardening:
    def test_websocket_handshake(self):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/voice/stream?session_id=h-test-01") as ws:
            handshake = ws.receive_json()
            assert handshake["type"] == "status"
            assert handshake["status"] == "connected"
            assert handshake["session_id"] == "h-test-01"

    def test_websocket_control_config(self):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/voice/stream") as ws:
            ws.receive_json()  # discard handshake
            
            # Send configuration start frame
            ws.send_json({"type": "start", "voice_profile": "loyal"})
            resp = ws.receive_json()
            assert resp["type"] == "status"
            assert resp["status"] == "active"

    def test_websocket_audio_turn_processing(self):
        client = TestClient(app)
        fake_stt = {"ok": True, "transcript": "system check", "confidence": 0.99, "language": "en"}
        fake_graph = {"result": "Status is stable, my lord.", "selected_agent": "Scientist", "risk_level": "low"}
        mock_pcm = [b"\xaa\xbb" * 10]

        with patch("backend.core.voice.runtime.websocket_protocol.StreamingSTT.transcribe_segment", return_value=fake_stt), \
             patch("backend.core.voice.runtime.websocket_protocol._run_graph", return_value=fake_graph), \
             patch("backend.core.voice.runtime.streaming_tts.StreamingTTS._stream_fallback", return_value=mock_pcm):

            with client.websocket_connect("/api/v1/voice/stream") as ws:
                ws.receive_json()  # discard handshake

                # Send 1st speech frame (RMS ~0.26)
                speech_chunk = b"\x55" * 320
                ws.send_bytes(speech_chunk)
                ws.send_bytes(speech_chunk)  # 2nd active frame -> triggers speech_start
                
                # Send 15 silent frames to trigger speech_end (turn commit)
                silent_chunk = b"\x00" * 320
                for _ in range(15):
                    ws.send_bytes(silent_chunk)

                # Read output responses:
                # 1. Transcript frame
                stt_pkt = ws.receive_json()
                assert stt_pkt["type"] == "transcript"
                assert stt_pkt["text"] == "system check"

                # 2. Binary audio frame
                chunk = ws.receive_bytes()
                assert chunk == b"\xaa\xbb" * 10

                # 3. Telemetry metrics
                metrics = ws.receive_json()
                assert metrics["type"] == "telemetry"
                assert "metrics" in metrics
