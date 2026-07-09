"""Unit tests for Program 30.0: Multi-Model Cognitive Runtime.

Verifies the KattappaModelRouter constraints, MultimodalContextBuffer sliding limits,
and CognitiveSessionOrchestrator barge-in voice loop triggers.
"""
from __future__ import annotations

import time
from typing import Generator

import pytest

from backend.core.model.router import KattappaModelRouter
from backend.core.voice.context_buffer import MultimodalContextBuffer
from backend.core.voice.orchestrator import CognitiveSessionOrchestrator


# ── Model Router Tests ────────────────────────────────────────────────────────

class TestModelRouter:
    def test_routing_by_offline_override(self):
        router = KattappaModelRouter()
        assert router.route_request("Complex query", force_offline=True) == "local"

    def test_routing_by_budget_limit(self):
        router = KattappaModelRouter()
        # Cost limit too tight for cloud ($0.01 limit vs $0.05 cloud threshold)
        assert router.route_request("Complex query", max_cost_usd=0.01) == "local"

    def test_routing_by_latency_limit(self):
        router = KattappaModelRouter()
        # Latency constraint requires local execution (100ms vs 150ms local threshold)
        assert router.route_request("Complex query", max_latency_ms=100.0) == "local"

    def test_routing_by_complexity_keywords(self):
        router = KattappaModelRouter()
        # Prompts containing keywords like plan/synthesize are routed to cloud
        assert router.route_request("Generate a system plan") == "cloud"
        assert router.route_request("A simple question") == "local"

    def test_routing_by_prompt_length(self):
        router = KattappaModelRouter()
        long_prompt = "word " * 60
        assert router.route_request(long_prompt) == "cloud"


# ── Context Buffer Tests ──────────────────────────────────────────────────────

class TestContextBuffer:
    def test_append_different_modalities(self):
        buf = MultimodalContextBuffer()
        buf.append_interaction("text", "Hello")
        buf.append_interaction("audio", "sample_wave_data")
        buf.append_interaction("image", "frame_1.jpg")
        buf.append_interaction("tool", "exec: ls")

        assert buf.size == 4
        flat = buf.get_flattened_context()
        assert flat[0]["modality"] == "text"
        assert flat[3]["modality"] == "tool"

    def test_invalid_modality_raises(self):
        buf = MultimodalContextBuffer()
        with pytest.raises(ValueError, match="Unsupported modality"):
            buf.append_interaction("video", "unsupported")

    def test_sliding_window_limit(self):
        buf = MultimodalContextBuffer(max_history_size=3)
        buf.append_interaction("text", "1")
        buf.append_interaction("text", "2")
        buf.append_interaction("text", "3")
        assert buf.size == 3
        
        # Adding 4th drops first entry
        buf.append_interaction("text", "4")
        assert buf.size == 3
        flat = buf.get_flattened_context()
        assert flat[0]["data"] == "2"
        assert flat[2]["data"] == "4"


# ── Session Orchestrator Tests ────────────────────────────────────────────────

class TestSessionOrchestrator:
    def test_barge_in_playback_interruption(self):
        orch = CognitiveSessionOrchestrator()
        
        # Simulate active TTS playback
        orch.is_playing_audio = True
        orch.audio_interrupted = False

        # VAD detects user speaking
        vad_fn = lambda x: True
        stt_fn = lambda x: ""

        orch.handle_input_audio_chunk(b"user_speech_chunk", vad_fn, stt_fn)
        
        # Audio playback should be stopped instantly
        assert orch.is_playing_audio is False
        assert orch.audio_interrupted is True

    def test_respond_streaming_completed(self):
        orch = CognitiveSessionOrchestrator()
        
        # Mock generator returning text tokens
        def mock_generator(prompt: str) -> Generator[str, None, None]:
            yield "Hello "
            yield "world"

        written_audio_chunks = []
        audio_writer = lambda chunk: written_audio_chunks.append(chunk)
        tts_fn = lambda token: f"audio_{token}".encode()

        orch.respond_streaming(
            prompt="Hi",
            response_generator=mock_generator,
            tts_fn=tts_fn,
            audio_writer=audio_writer,
        )

        assert orch.is_playing_audio is False
        assert len(written_audio_chunks) == 2
        assert written_audio_chunks[0] == b"audio_Hello "
        assert written_audio_chunks[1] == b"audio_world"
        
        # Verifies response logged to buffer
        flat = orch.context.get_flattened_context()
        assert flat[-1]["modality"] == "text"
        assert "world" in flat[-1]["data"]

    def test_respond_streaming_interrupted_on_barge_in(self):
        orch = CognitiveSessionOrchestrator()

        def mock_generator(prompt: str) -> Generator[str, None, None]:
            yield "Token 1 "
            # Simulate a user barge-in event happening asynchronously during generation
            orch.audio_interrupted = True
            yield "Token 2"

        written_audio_chunks = []
        audio_writer = lambda chunk: written_audio_chunks.append(chunk)
        tts_fn = lambda token: f"audio_{token}".encode()

        orch.respond_streaming(
            prompt="Hi",
            response_generator=mock_generator,
            tts_fn=tts_fn,
            audio_writer=audio_writer,
        )

        # Loop should terminate instantly after first token due to barge-in interrupt
        assert len(written_audio_chunks) == 1
        assert written_audio_chunks[0] == b"audio_Token 1 "
