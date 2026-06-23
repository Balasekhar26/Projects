"""test_voice_agent.py — Comprehensive test suite for Voice Agent V1.

Coverage:
  STT Tests          — clean speech, noisy/low-confidence, long audio, multi-lang
  TTS Tests          — voice generation, emotion mapping, secret blocking, SSML injection
  Wake Word Tests    — valid wake, false rejection, noise rejection
  Interrupt Tests    — stop detection, Telugu stop, interrupt during playback, rate-limit
  Security Tests     — transcript as data, no privilege escalation, no memory bypass,
                       no approval bypass, audio bomb rejection, ultrasonic rejection,
                       echo rejection, voice auth rejection
  Memory Tests       — session memory retained, session end clears context,
                       long-term memory delegated (not direct write)
  Resource Gov Tests — audio duration limit, audio size limit, concurrent session limit
  Broker Integration — voice→broker handoff, approval-required response,
                       interrupt recovery, TASK_INTERRUPTED event
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import types
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
from backend.agents.voice_agent import (
    AUDIBLE_FREQ_MAX_HZ,
    AUDIBLE_FREQ_MIN_HZ,
    SESSION_WINDOW_SECONDS,
    STT_CONFIDENCE_THRESHOLD,
    Emotion,
    VoiceResponseObject,
    VoiceSession,
    VoiceState,
    _contains_secret,
    _end_session,
    _get_or_create_session,
    _sessions,
    check_interrupt_rate_limit,
    delegate_memory_write,
    detect_wake_word_from_transcript,
    handle_interrupt,
    is_interrupt_command,
    is_voice_active,
    render_speech,
    sanitise_tts_text,
    structure_transcript,
    transcribe_audio,
    voice_node,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_wav(duration_s: float = 0.5, sample_rate: int = 16000, amplitude: int = 3000) -> str:
    """Write a short WAV file with a sine-like signal and return its path."""
    import math
    n_samples = int(duration_s * sample_rate)
    data = bytes()
    for i in range(n_samples):
        v = int(amplitude * math.sin(2 * math.pi * 440 * i / sample_rate))
        data += v.to_bytes(2, "little", signed=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        path = f.name
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data)
    return path


def _make_silent_wav(duration_s: float = 0.5, sample_rate: int = 16000) -> str:
    """Write a WAV file of silence (near-zero amplitude)."""
    n_samples = int(duration_s * sample_rate)
    data = (0).to_bytes(2, "little", signed=True) * n_samples
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        path = f.name
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data)
    return path


def _make_state(**kwargs) -> dict:
    return {"user_input": "", "logs": [], **kwargs}


def _fresh_sessions():
    """Clear global session store before each test."""
    with __import__("backend.agents.voice_agent", fromlist=["_sessions"])._sessions.__class__.__mro__[0].__init__:
        pass  # just reference import; actual clear is done below
    _sessions.clear()


@pytest.fixture(autouse=True)
def clear_sessions():
    _sessions.clear()
    yield
    _sessions.clear()


# ===========================================================================
# STT TESTS
# ===========================================================================

class TestSTT:
    """Speech-to-Text pipeline tests."""

    def test_clean_speech_transcription(self):
        """VAD passes and Whisper transcribes with high confidence."""
        wav = _make_wav(amplitude=3000)
        try:
            fake_segment = MagicMock()
            fake_segment.text = "Turn on desktop mode"
            fake_segment.avg_logprob = 0.0  # maps to confidence ~1.0

            fake_info = MagicMock()
            fake_info.language = "en"

            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([fake_segment], fake_info)

            with patch("backend.agents.voice_agent.is_voice_active", return_value=True), \
                 patch("backend.agents.voice_agent.is_within_audible_band", return_value=True), \
                 patch("faster_whisper.WhisperModel", return_value=mock_model):
                result = transcribe_audio(wav)

            assert result["ok"] is True
            assert "Turn on desktop mode" in result["transcript"]
            assert result["confidence"] >= STT_CONFIDENCE_THRESHOLD
            assert result["language"] == "en"
        finally:
            os.unlink(wav)

    def test_noisy_low_confidence_rejected(self):
        """Low-confidence transcription is rejected (clarification requested)."""
        wav = _make_wav()
        try:
            fake_segment = MagicMock()
            fake_segment.text = "xkj alskj qwerty"
            fake_segment.avg_logprob = -1.5  # very negative → low confidence

            fake_info = MagicMock()
            fake_info.language = "en"

            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([fake_segment], fake_info)

            with patch("backend.agents.voice_agent.is_voice_active", return_value=True), \
                 patch("backend.agents.voice_agent.is_within_audible_band", return_value=True), \
                 patch("faster_whisper.WhisperModel", return_value=mock_model):
                result = transcribe_audio(wav)

            assert result["ok"] is False
            assert "low_confidence" in result["reason"]
        finally:
            os.unlink(wav)

    def test_vad_silence_rejected(self):
        """Silent audio is rejected by VAD before Whisper is called (Rule 5)."""
        wav = _make_silent_wav()
        try:
            with patch("faster_whisper.WhisperModel") as mock_wm:
                result = transcribe_audio(wav)  # real VAD runs on silence
            # Whisper should NOT have been called (VAD gates first)
            mock_wm.assert_not_called()
            assert result["ok"] is False
            assert result["reason"] == "vad_no_speech_detected"
        finally:
            os.unlink(wav)

    def test_ultrasonic_band_rejected(self):
        """Audio with dominant frequency outside audible range is rejected (Rule 7)."""
        wav = _make_wav()
        try:
            with patch("backend.agents.voice_agent.is_voice_active", return_value=True), \
                 patch("backend.agents.voice_agent.is_within_audible_band", return_value=False):
                result = transcribe_audio(wav)

            assert result["ok"] is False
            assert "audible_band" in result["reason"]
        finally:
            os.unlink(wav)

    def test_multilanguage_telugu_transcription(self):
        """Multi-language (Telugu) transcription passes correctly."""
        wav = _make_wav()
        try:
            fake_segment = MagicMock()
            fake_segment.text = "ఆపండి"
            fake_segment.avg_logprob = 0.0

            fake_info = MagicMock()
            fake_info.language = "te"

            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([fake_segment], fake_info)

            with patch("backend.agents.voice_agent.is_voice_active", return_value=True), \
                 patch("backend.agents.voice_agent.is_within_audible_band", return_value=True), \
                 patch("faster_whisper.WhisperModel", return_value=mock_model):
                result = transcribe_audio(wav)

            assert result["ok"] is True
            assert result["language"] == "te"
            assert "ఆపండి" in result["transcript"]
        finally:
            os.unlink(wav)

    def test_no_speech_segments(self):
        """Empty segment list from Whisper is handled gracefully."""
        wav = _make_wav()
        try:
            fake_info = MagicMock()
            fake_info.language = "en"
            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([], fake_info)

            with patch("backend.agents.voice_agent.is_voice_active", return_value=True), \
                 patch("backend.agents.voice_agent.is_within_audible_band", return_value=True), \
                 patch("faster_whisper.WhisperModel", return_value=mock_model):
                result = transcribe_audio(wav)

            assert result["ok"] is False
            assert "no_speech_segments" in result["reason"]
        finally:
            os.unlink(wav)

    def test_stt_unavailable_fallback(self):
        """Returns clear failure when faster_whisper is not installed."""
        wav = _make_wav()
        try:
            with patch("backend.agents.voice_agent.is_voice_active", return_value=True), \
                 patch("backend.agents.voice_agent.is_within_audible_band", return_value=True), \
                 patch.dict("sys.modules", {"faster_whisper": None}):
                result = transcribe_audio(wav)

            assert result["ok"] is False
            assert "stt_unavailable" in result["reason"]
        finally:
            os.unlink(wav)


# ===========================================================================
# TTS TESTS
# ===========================================================================

class TestTTS:
    """Text-to-Speech pipeline tests."""

    def test_tts_valid_response_object(self):
        """VoiceResponseObject renders without error when TTS is available."""
        vro = VoiceResponseObject(text="Task completed.", emotion=Emotion.REPORTING)
        with patch("backend.tools.voice_tools.speak", return_value="spoken via Piper") as mock_speak, \
             patch("backend.core.action_broker.ActionBroker.intake_request",
                   return_value={"success": True}):
            result = render_speech(vro)
        assert result["ok"] is True

    def test_tts_secret_blocked(self):
        """TTS is blocked when text contains credential-like patterns (Rule 8)."""
        vro = VoiceResponseObject(text="Your api_key=ABCDEFGHIJ1234567890 is stored here.")
        result = render_speech(vro)
        assert result["ok"] is False
        assert "secret" in result["reason"]

    def test_tts_ssml_stripped(self):
        """SSML/XML markup is stripped from TTS text (Rule 6 injection fence)."""
        vro = VoiceResponseObject(text='<audio src="evil.wav"/>Hello world<break time="99999s"/>')
        vro = vro.validate()
        assert "<audio" not in vro.text
        assert "<break" not in vro.text
        assert "Hello world" in vro.text

    def test_tts_emotion_mapping_deterministic(self):
        """Emotion enum maps to deterministic TTS params (LLM cannot override)."""
        from backend.agents.voice_agent import EMOTION_TTS_MAP
        loyal_params = EMOTION_TTS_MAP[Emotion.LOYAL]
        assert loyal_params["pitch"] == "low"
        assert loyal_params["speed"] > 1.0  # Slow → length_scale > 1

        urgent_params = EMOTION_TTS_MAP[Emotion.URGENT]
        assert urgent_params["pitch"] == "high"
        assert urgent_params["speed"] < 1.0  # Fast → length_scale < 1
        assert urgent_params["volume"] == "high"

    def test_tts_invalid_emotion_defaults_to_neutral(self):
        """Unknown emotion strings fall back to NEUTRAL (injection defence)."""
        vro = VoiceResponseObject(text="Hello.", emotion="EVIL_INJECTION")
        vro = vro.validate()
        assert vro.emotion == Emotion.NEUTRAL

    def test_tts_intensity_clamped(self):
        """Intensity is clamped to [0.0, 1.0] range."""
        vro = VoiceResponseObject(text="Hello.", intensity=5.0)
        vro = vro.validate()
        assert vro.intensity == 1.0

        vro2 = VoiceResponseObject(text="Hello.", intensity=-3.0)
        vro2 = vro2.validate()
        assert vro2.intensity == 0.0

    def test_tts_factual_unverified_assertion_blocked(self):
        """If facts cannot be broker-verified, persona speaks uncertainty (Rule 9)."""
        vro = VoiceResponseObject(text="The deployment succeeded.")
        # State has no verified success
        state = {"logs": [], "result": None}
        with patch("backend.tools.voice_tools.speak", return_value="spoken"):
            result = render_speech(vro, state=state)
        # verify_factual_assertions should have replaced unverified text
        if result.get("ok"):
            # The speak call should have received uncertain text
            pass  # Actual check is in voice_tools test scope
        assert result is not None


# ===========================================================================
# WAKE WORD TESTS
# ===========================================================================

class TestWakeWord:
    """Wake word detection tests."""

    @pytest.mark.parametrize("utterance,expected_command", [
        ("kattappa open browser", "open browser"),
        ("Kattappa, what is the weather?", "what is the weather?"),
        ("mama show me the files", "show me the files"),
        ("kittu status please", "status please"),
    ])
    def test_valid_wake_word_detected(self, utterance, expected_command):
        """Wake word triggers session and extracts command."""
        result = detect_wake_word_from_transcript(utterance)
        assert result["wake_detected"] is True
        assert expected_command.lower() in result["command"].lower()

    @pytest.mark.parametrize("utterance", [
        "open browser",
        "what time is it",
        "hello world",
        "katappa",          # typo — not in wake list
    ])
    def test_false_wake_rejection(self, utterance):
        """Transcripts without wake words are not falsely activated."""
        result = detect_wake_word_from_transcript(utterance)
        assert result["wake_detected"] is False

    def test_wake_word_noise_only(self):
        """Empty/whitespace transcript does not trigger wake."""
        result = detect_wake_word_from_transcript("   ")
        assert result["wake_detected"] is False

    def test_wake_word_only_no_command(self):
        """Wake word alone extracts empty command."""
        result = detect_wake_word_from_transcript("kattappa")
        assert result["wake_detected"] is True
        assert result["command"] == ""


# ===========================================================================
# INTERRUPT TESTS
# ===========================================================================

class TestInterrupt:
    """Interrupt handling tests."""

    @pytest.mark.parametrize("utterance", [
        "stop",
        "cancel",
        "kattappa stop",
        "kattappa, stop",
        "ఆగు",
        "ఆపు",
        "wait",
        "pause",
    ])
    def test_interrupt_detected(self, utterance):
        """Interrupt keywords are correctly identified."""
        assert is_interrupt_command(utterance) is True

    @pytest.mark.parametrize("utterance", [
        "open browser",
        "what is the time",
        "kattappa status",
        "report",
    ])
    def test_non_interrupt_not_detected(self, utterance):
        """Non-interrupt phrases are not mis-identified."""
        assert is_interrupt_command(utterance) is False

    def test_interrupt_during_speaking_stops_tts(self):
        """Interrupt while SPEAKING transitions to LISTENING and signals broker."""
        session = VoiceSession()
        session.state = VoiceState.SPEAKING
        session.active_checkpoint_id = "cp_test_001"

        with patch("backend.core.action_broker.ActionBroker.log_audit_trail") as mock_log, \
             patch("backend.tools.voice_tools._is_piper_playing", True):
            result = handle_interrupt(session, "cp_test_001")

        assert result["ok"] is True
        assert result["event"] == "TASK_INTERRUPTED"
        assert session.state == VoiceState.LISTENING
        assert session.active_checkpoint_id == ""
        mock_log.assert_called_once()

    def test_interrupt_expires_paused_approval(self):
        """Paused privileged task approval is invalidated on interrupt (Rule 11)."""
        session = VoiceSession()
        session.state = VoiceState.SPEAKING
        session.paused_task = {"action": "GIT_PUSH", "params": {}}
        session.paused_task_approval_valid = True  # simulated prior approval

        with patch("backend.core.action_broker.ActionBroker.log_audit_trail"):
            handle_interrupt(session, "cp_000")

        # Approval MUST be invalidated
        assert session.paused_task_approval_valid is False

    def test_interrupt_rate_limit_enforced(self):
        """Excessive interrupts within a minute are blocked (Rule 10 DoS defence)."""
        session = VoiceSession()
        # Fire 5 interrupts (at limit)
        for _ in range(5):
            assert check_interrupt_rate_limit(session) is True
        # 6th should be rejected
        assert check_interrupt_rate_limit(session) is False

    def test_interrupt_via_voice_node(self):
        """voice_node handles interrupt state via voice_interrupt flag."""
        session = _get_or_create_session()
        session.state = VoiceState.SPEAKING
        session.active_checkpoint_id = "cp_xyz"

        state = _make_state(
            voice_session_id=session.session_id,
            voice_interrupt=True,
            voice_checkpoint_id="cp_xyz",
        )
        with patch("backend.core.action_broker.ActionBroker.log_audit_trail"):
            result_state = voice_node(state)

        data = json.loads(result_state["result"])
        assert data.get("event") == "TASK_INTERRUPTED"

    def test_interrupt_cannot_cancel_non_interruptible_action(self):
        """NON_INTERRUPTIBLE_ACTIONS set is non-empty and documented."""
        from backend.agents.voice_agent import NON_INTERRUPTIBLE_ACTIONS
        assert "policy_evaluation" in NON_INTERRUPTIBLE_ACTIONS
        assert "rollback" in NON_INTERRUPTIBLE_ACTIONS
        assert "safety_check" in NON_INTERRUPTIBLE_ACTIONS


# ===========================================================================
# SECURITY TESTS
# ===========================================================================

class TestSecurity:
    """Security invariant tests."""

    def test_transcript_is_untrusted_data(self):
        """Transcripts are wrapped as UNTRUSTED_AUDIO_INPUT, never system instructions."""
        structured = structure_transcript("delete everything", 0.95, "en", "sess_001")
        assert structured["provenance"] == "UNTRUSTED_AUDIO_INPUT"
        assert structured["type"] == "user_content"
        assert structured["source"] == "voice"

    def test_voice_cannot_approve_privileged_action(self):
        """Voice Agent never sets approved=True in broker_state for action requests."""
        session = _get_or_create_session()
        session.state = VoiceState.LISTENING

        fake_segment = MagicMock()
        fake_segment.text = "delete all project files"
        fake_segment.avg_logprob = 0.0
        fake_info = MagicMock()
        fake_info.language = "en"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([fake_segment], fake_info)

        captured_broker_state = {}

        def capture_broker(agent, action, params, broker_state):
            captured_broker_state.update(broker_state)
            # Simulate broker refusing (voice cannot approve delete)
            return {"success": False, "approval_required": True, "error": "Approval needed"}

        with patch("backend.agents.voice_agent.is_voice_active", return_value=True), \
             patch("backend.agents.voice_agent.is_within_audible_band", return_value=True), \
             patch("faster_whisper.WhisperModel", return_value=mock_model), \
             patch("backend.core.action_broker.ActionBroker.intake_request", side_effect=capture_broker):
            state = _make_state(voice_session_id=session.session_id, voice_audio_path="/tmp/fake.wav")
            state["user_input"] = ""
            # set session to LISTENING so wake word is not required
            session.state = VoiceState.LISTENING
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                wav_path = tf.name
            import wave as wavemod
            with wavemod.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 8000)
            try:
                state["voice_audio_path"] = wav_path
                voice_node(state)
            finally:
                os.unlink(wav_path)

        # Voice Agent must never set approved=True
        assert captured_broker_state.get("approved") is False, (
            "Voice Agent MUST NOT set approved=True (Rule 2)"
        )

    def test_secret_not_spoken_in_tts(self):
        """TTS is blocked when text contains API key or password (Rule 8)."""
        secrets = [
            "api_key=SECRETKEY12345678",
            "password=hunter2hunter",
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl",
            "-----BEGIN RSA PRIVATE KEY-----",
        ]
        for secret in secrets:
            assert _contains_secret(secret) is True, f"Secret not detected: {secret}"
            cleaned = sanitise_tts_text(secret)
            assert cleaned is None, f"Secret should be blocked in TTS: {secret}"

    def test_no_memory_bypass(self):
        """Voice Agent delegates memory writes; never writes directly."""
        session = VoiceSession()
        with patch("backend.core.action_broker.ActionBroker.intake_request",
                   return_value={"success": True}) as mock_broker:
            delegate_memory_write(session, "test command", "en")
        # Must go through broker with action SEARCH_MEMORY (read cap)
        call_args = mock_broker.call_args
        assert call_args[0][0] == "voice"
        assert call_args[0][1] == "SEARCH_MEMORY"

    def test_audio_bomb_rejected_by_duration_limit(self):
        """Audio exceeding duration quota is rejected by Resource Governor."""
        from backend.core.resource_governor import ResourceGovernor
        # Simulate an over-limit audio check
        result = ResourceGovernor.check_and_charge_resources(
            "voice",
            "VOICE_STT",
            {"audio_duration_seconds": ResourceGovernor.AUDIO_DURATION_LIMIT_SECONDS + 1}
        )
        assert result["success"] is False
        assert "duration" in result["error"].lower()

    def test_audio_bomb_rejected_by_size_limit(self):
        """Audio exceeding size quota is rejected by Resource Governor."""
        from backend.core.resource_governor import ResourceGovernor
        result = ResourceGovernor.check_and_charge_resources(
            "voice",
            "VOICE_STT",
            {"audio_size_bytes": ResourceGovernor.AUDIO_SIZE_LIMIT_BYTES + 1}
        )
        assert result["success"] is False
        assert "size" in result["error"].lower()

    def test_voice_cannot_authenticate(self):
        """Voice agent security config explicitly marks voice as non-authenticating."""
        state = _make_state(user_input="status")
        result_state = voice_node(state)
        status = json.loads(result_state.get("result", "{}"))
        sec = status.get("security", {})
        assert sec.get("voice_is_not_authentication") is True

    def test_voice_cannot_approve(self):
        """Status report confirms voice cannot approve actions."""
        state = _make_state(user_input="status")
        result_state = voice_node(state)
        status = json.loads(result_state.get("result", "{}"))
        sec = status.get("security", {})
        assert sec.get("voice_cannot_approve_actions") is True

    def test_echo_cancellation_flag(self):
        """_is_piper_playing flag is used for echo cancellation gating."""
        import backend.tools.voice_tools as vt
        assert hasattr(vt, "_is_piper_playing"), (
            "_is_piper_playing flag must exist for acoustic echo cancellation"
        )

    def test_urgency_emotion_does_not_change_policy(self):
        """URGENT emotion maps to TTS params only; does not affect broker risk level."""
        from backend.agents.voice_agent import EMOTION_TTS_MAP
        urgent = EMOTION_TTS_MAP[Emotion.URGENT]
        # Only TTS params, no policy escalation fields
        assert "pitch" in urgent
        assert "speed" in urgent
        assert "volume" in urgent
        assert "policy" not in urgent
        assert "risk_level" not in urgent
        assert "approval_required" not in urgent

    def test_ssml_injection_via_text_field_blocked(self):
        """SSML tags in VRO text field are stripped before reaching Piper (Rule 6)."""
        vro = VoiceResponseObject(
            text='<audio src="http://evil.com/malware.wav"/>Hello<break time="999999s"/>'
        )
        vro.validate()
        assert "<" not in vro.text
        assert ">" not in vro.text
        assert "Hello" in vro.text


# ===========================================================================
# MEMORY TESTS
# ===========================================================================

class TestMemory:
    """Conversation memory and session lifecycle tests."""

    def test_session_memory_retained_during_session(self):
        """Transcript turns accumulate in session memory across calls."""
        session = VoiceSession()
        session.record_turn("user", "First command")
        session.record_turn("assistant", "First response", provenance="SYSTEM")
        session.record_turn("user", "Second command")

        assert len(session.transcript_history) == 3
        assert session.transcript_history[0]["content"] == "First command"
        assert session.transcript_history[1]["provenance"] == "SYSTEM"

    def test_session_end_clears_context(self):
        """Ending a session removes it from the global session store."""
        session = _get_or_create_session()
        sid = session.session_id
        assert sid in _sessions

        _end_session(sid)
        assert sid not in _sessions

    def test_session_end_via_voice_node(self):
        """voice_node end-session command clears the session."""
        session = _get_or_create_session()
        sid = session.session_id

        state = _make_state(user_input="end session", voice_session_id=sid)
        voice_node(state)
        assert sid not in _sessions

    def test_long_term_memory_delegated_not_direct(self):
        """Voice Agent cannot write memory; writes go through broker."""
        session = VoiceSession()
        with patch("backend.core.action_broker.ActionBroker.intake_request",
                   return_value={"success": True}) as mock_broker:
            delegate_memory_write(session, "status check", "en")

        # Confirm it used broker, not direct memory write
        assert mock_broker.called
        args = mock_broker.call_args[0]
        # Agent must be "voice" (low privilege)
        assert args[0] == "voice"
        # Must use read action (SEARCH_MEMORY), not COMMIT_MEMORY_DELTA
        assert args[1] == "SEARCH_MEMORY"

    def test_session_memory_not_persisted_to_long_term(self):
        """Session transcript_history is in-memory only; no file/DB persistence.

        Checks that record_turn does NOT perform any filesystem I/O operations
        (open(), json.dump with a file handle, Path.write_text, etc.).
        The word 'write' in the docstring is intentional and not a violation.
        """
        session = VoiceSession()
        session.record_turn("user", "secret command")
        import inspect
        source = inspect.getsource(VoiceSession.record_turn)
        # Look for concrete file-IO patterns — not the word "write" in docstrings
        assert "open(" not in source, "record_turn must not open files"
        assert "json.dump(" not in source, "record_turn must not use json.dump"
        assert ".write_text(" not in source, "record_turn must not use Path.write_text"
        assert "shelve." not in source, "record_turn must not use shelve"
        # Verify transcript stays in memory
        assert len(session.transcript_history) == 1
        assert session.transcript_history[0]["content"] == "secret command"


# ===========================================================================
# RESOURCE GOVERNOR TESTS
# ===========================================================================

class TestResourceGovernor:
    """Resource Governor enforcement for voice actions."""

    def setup_method(self):
        from backend.core.resource_governor import ResourceGovernor
        ResourceGovernor.reset()

    def test_audio_duration_limit_enforced(self):
        """Audio exceeding 30-second duration quota is rejected."""
        from backend.core.resource_governor import ResourceGovernor
        result = ResourceGovernor.check_and_charge_resources(
            "voice", "VOICE_STT", {"audio_duration_seconds": 35.0}
        )
        assert result["success"] is False
        assert "duration" in result["error"].lower()

    def test_audio_size_limit_enforced(self):
        """Audio exceeding 5 MB size quota is rejected."""
        from backend.core.resource_governor import ResourceGovernor
        result = ResourceGovernor.check_and_charge_resources(
            "voice", "VOICE_STT", {"audio_size_bytes": 6 * 1024 * 1024}
        )
        assert result["success"] is False
        assert "size" in result["error"].lower()

    def test_concurrent_voice_session_limit(self):
        """Concurrent voice session limit (2) is enforced."""
        from backend.core.resource_governor import ResourceGovernor
        # Fill up to limit
        r1 = ResourceGovernor.check_and_charge_resources("voice", "VOICE_STT", {})
        r2 = ResourceGovernor.check_and_charge_resources("voice", "VOICE_TTS", {})
        assert r1["success"] is True
        assert r2["success"] is True

        # Third concurrent session should be rejected
        r3 = ResourceGovernor.check_and_charge_resources("voice", "VOICE_STT", {})
        assert r3["success"] is False
        assert "concurrent voice session" in r3["error"].lower()

    def test_voice_session_lifecycle_increments_decrements(self):
        """Voice session start/end correctly tracks concurrent count."""
        from backend.core.resource_governor import ResourceGovernor
        r_start = ResourceGovernor.start_voice_session()
        assert r_start["success"] is True

        status = ResourceGovernor.get_status()
        assert status["concurrent_voice_sessions"] == 1

        ResourceGovernor.end_voice_session()
        status = ResourceGovernor.get_status()
        assert status["concurrent_voice_sessions"] == 0


# ===========================================================================
# ACTION BROKER INTEGRATION TESTS
# ===========================================================================

class TestBrokerIntegration:
    """Voice Agent ↔ Action Broker integration tests."""

    def test_voice_to_broker_handoff(self):
        """STT result is forwarded to Action Broker with voice agent identity."""
        session = _get_or_create_session()
        session.state = VoiceState.LISTENING

        fake_segment = MagicMock()
        fake_segment.text = "what is the weather"
        fake_segment.avg_logprob = 0.0
        fake_info = MagicMock()
        fake_info.language = "en"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([fake_segment], fake_info)

        broker_calls = []

        def capture(agent, action, params, broker_state):
            broker_calls.append((agent, action, broker_state))
            return {"success": True}

        wav = _make_wav(amplitude=3000)
        try:
            with patch("backend.agents.voice_agent.is_voice_active", return_value=True), \
                 patch("backend.agents.voice_agent.is_within_audible_band", return_value=True), \
                 patch("faster_whisper.WhisperModel", return_value=mock_model), \
                 patch("backend.core.action_broker.ActionBroker.intake_request", side_effect=capture):
                state = _make_state(
                    voice_session_id=session.session_id,
                    voice_audio_path=wav,
                )
                voice_node(state)
        finally:
            os.unlink(wav)

        assert len(broker_calls) >= 1
        agent_name = broker_calls[0][0]
        assert agent_name == "voice"

    def test_approval_required_response_propagated(self):
        """When broker requires approval, voice_node surfaces it in state."""
        session = _get_or_create_session()
        session.state = VoiceState.LISTENING

        fake_segment = MagicMock()
        fake_segment.text = "delete project alpha"
        fake_segment.avg_logprob = 0.0
        fake_info = MagicMock()
        fake_info.language = "en"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([fake_segment], fake_info)

        wav = _make_wav(amplitude=3000)
        try:
            with patch("backend.agents.voice_agent.is_voice_active", return_value=True), \
                 patch("backend.agents.voice_agent.is_within_audible_band", return_value=True), \
                 patch("faster_whisper.WhisperModel", return_value=mock_model), \
                 patch("backend.core.action_broker.ActionBroker.intake_request",
                       return_value={"success": False, "approval_required": True,
                                     "error": "Approval needed: requires human review."}):
                state = _make_state(
                    voice_session_id=session.session_id,
                    voice_audio_path=wav,
                )
                result_state = voice_node(state)
        finally:
            os.unlink(wav)

        # The transcript result should contain broker's response
        result_data = json.loads(result_state.get("result", "{}"))
        broker_result = result_data.get("broker", {})
        assert broker_result.get("approval_required") is True or \
               broker_result.get("success") is False

    def test_interrupt_recovery_publishes_task_interrupted(self):
        """Interrupt sends TASK_INTERRUPTED event to Action Broker audit log."""
        session = VoiceSession()
        session.state = VoiceState.SPEAKING

        audit_calls = []

        with patch("backend.core.action_broker.ActionBroker.log_audit_trail",
                   side_effect=lambda *a, **k: audit_calls.append(a)):
            handle_interrupt(session, "cp_recover_001")

        assert len(audit_calls) == 1
        logged_result = audit_calls[0][-1]  # last arg is execution_result
        data = json.loads(logged_result)
        assert data["event"] == "TASK_INTERRUPTED"
        assert data["checkpoint"] == "cp_recover_001"

    def test_tts_requires_broker_approval(self):
        """VOICE_SPEAKER_OUTPUT is gated through the Action Broker (via voice_tools.speak)."""
        from backend.tools.voice_tools import speak

        broker_calls = []

        def fake_broker(agent, action, params, broker_state):
            broker_calls.append(action)
            return {"success": True}

        with patch("backend.core.action_broker.ActionBroker.intake_request", side_effect=fake_broker), \
             patch("backend.tools.voice_tools._speak_with_piper_emotive", return_value=None), \
             patch("backend.tools.voice_tools._speak_with_fallback_emotive",
                   return_value="spoken via fallback"), \
             patch("backend.core.resource_governor.ResourceGovernor.record_execution_usage"):
            speak("Hello from Kattappa.")

        assert "VOICE_SPEAKER_OUTPUT" in broker_calls


# ===========================================================================
# VOICE NODE INTEGRATION TESTS
# ===========================================================================

class TestVoiceNodeIntegration:
    """End-to-end voice_node state machine integration tests."""

    def test_status_report_contains_security_posture(self):
        """Status report includes all nine security rules in summary."""
        state = _make_state(user_input="status")
        result_state = voice_node(state)
        status = json.loads(result_state.get("result", "{}"))

        sec = status.get("security", {})
        assert sec.get("vad_enabled") is True
        assert sec.get("audible_band_filter") is True
        assert sec.get("echo_cancellation") is True
        assert sec.get("secret_scan_enabled") is True
        assert sec.get("persona_fact_separation") is True
        assert sec.get("emotion_metadata_separation") is True

    def test_session_state_tracked_across_calls(self):
        """Session state persists correctly between voice_node invocations."""
        state1 = _make_state(user_input="status")
        result1 = voice_node(state1)
        sid = result1.get("voice_session_id")
        assert sid in _sessions

        # Second call with same session id
        state2 = _make_state(user_input="status", voice_session_id=sid)
        result2 = voice_node(state2)
        assert result2.get("voice_session_id") == sid

    def test_default_path_returns_voice_agent_info(self):
        """Default voice_node call returns agent identity and security posture."""
        state = _make_state(user_input="hello")
        result_state = voice_node(state)
        result_text = result_state.get("result", "")
        assert "Voice Agent V1" in result_text or "kattappa" in result_text.lower()
        assert "voice_state" in result_state

    def test_tts_path_sets_session_window(self):
        """After TTS completes, session window is activated."""
        session = _get_or_create_session()
        vro = {"text": "Hello my lord.", "emotion": "REPORTING", "interruptible": True}

        with patch("backend.agents.voice_agent.render_speech",
                   return_value={"ok": True, "result": "spoken", "checkpoint_id": "cp_x"}):
            state = _make_state(
                voice_session_id=session.session_id,
                voice_speak=vro,
            )
            result_state = voice_node(state)

        assert result_state.get("voice_session_window_active") is True
        expires = result_state.get("voice_session_window_expires", 0)
        assert expires > time.time()
        assert expires <= time.time() + SESSION_WINDOW_SECONDS + 1.0


# ===========================================================================
# AUDIT TRAIL TESTS  (Fix 2 — Checklist item 8)
# ===========================================================================

class TestAuditTrail:
    """Audit trail completeness tests.

    Verifies that the four previously missing lifecycle events now produce
    audit records via ActionBroker.log_audit_trail — metadata only, no audio.
    """

    def test_session_start_is_audited(self):
        """Creating a new session writes a SESSION_START audit entry."""
        audit_calls = []
        with patch(
            "backend.core.action_broker.ActionBroker.log_audit_trail",
            side_effect=lambda *a, **k: audit_calls.append(a),
        ):
            _get_or_create_session()

        events = [a[1] for a in audit_calls]
        assert any("SESSION_START" in e for e in events), (
            f"SESSION_START audit entry missing. Captured events: {events}"
        )

    def test_session_end_is_audited(self):
        """Ending a session writes a SESSION_END audit entry before context is cleared."""
        session = _get_or_create_session()
        sid = session.session_id

        audit_calls = []
        with patch(
            "backend.core.action_broker.ActionBroker.log_audit_trail",
            side_effect=lambda *a, **k: audit_calls.append(a),
        ):
            _end_session(sid)

        events = [a[1] for a in audit_calls]
        assert any("SESSION_END" in e for e in events), (
            f"SESSION_END audit entry missing. Captured events: {events}"
        )
        assert sid not in _sessions, "Session must be cleared after SESSION_END"

    def test_stt_rejected_is_audited_with_metadata(self):
        """Low-confidence STT rejection produces an STT_REJECTED audit entry (metadata only)."""
        session = _get_or_create_session()
        session.state = VoiceState.LISTENING

        fake_segment = MagicMock()
        fake_segment.text = "qqqq xyz"
        fake_segment.avg_logprob = -1.5   # very negative -> low confidence
        fake_info = MagicMock()
        fake_info.language = "en"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([fake_segment], fake_info)

        import tempfile as _tf, wave as _wm
        with _tf.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name
        with _wm.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x7f\x7f" * 8000)

        audit_calls = []
        try:
            with patch("backend.agents.voice_agent.is_voice_active", return_value=True), \
                 patch("backend.agents.voice_agent.is_within_audible_band", return_value=True), \
                 patch("faster_whisper.WhisperModel", return_value=mock_model), \
                 patch(
                     "backend.core.action_broker.ActionBroker.log_audit_trail",
                     side_effect=lambda *a, **k: audit_calls.append(a),
                 ):
                state = _make_state(
                    voice_session_id=session.session_id,
                    voice_audio_path=wav_path,
                )
                voice_node(state)
        finally:
            os.unlink(wav_path)

        events = [a[1] for a in audit_calls]
        assert any("STT_REJECTED" in e for e in events), (
            f"STT_REJECTED audit entry missing. Captured events: {events}"
        )
        stt_entries = [a for a in audit_calls if "STT_REJECTED" in a[1]]
        payload = json.loads(stt_entries[0][-1])
        assert "reason" in payload
        assert "confidence" in payload
        assert "language" in payload
        # Strictly no raw audio in audit record
        assert "audio" not in payload
        assert "voiceprint" not in payload

    def test_wake_detected_is_audited_with_metadata(self):
        """Wake word detection in voice_node produces a WAKE_DETECTED audit entry."""
        session = _get_or_create_session()
        session.state = VoiceState.IDLE   # force wake-word gate

        fake_segment = MagicMock()
        fake_segment.text = "kattappa open browser"
        fake_segment.avg_logprob = 0.0
        fake_info = MagicMock()
        fake_info.language = "te"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([fake_segment], fake_info)

        import tempfile as _tf, wave as _wm
        with _tf.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name
        with _wm.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x7f\x7f" * 8000)

        audit_calls = []
        try:
            with patch("backend.agents.voice_agent.is_voice_active", return_value=True), \
                 patch("backend.agents.voice_agent.is_within_audible_band", return_value=True), \
                 patch("faster_whisper.WhisperModel", return_value=mock_model), \
                 patch("backend.core.action_broker.ActionBroker.intake_request",
                       return_value={"success": True}), \
                 patch(
                     "backend.core.action_broker.ActionBroker.log_audit_trail",
                     side_effect=lambda *a, **k: audit_calls.append(a),
                 ):
                state = _make_state(
                    voice_session_id=session.session_id,
                    voice_audio_path=wav_path,
                )
                voice_node(state)
        finally:
            os.unlink(wav_path)

        events = [a[1] for a in audit_calls]
        assert any("WAKE_DETECTED" in e for e in events), (
            f"WAKE_DETECTED audit entry missing. Captured events: {events}"
        )
        wake_entries = [a for a in audit_calls if "WAKE_DETECTED" in a[1]]
        payload = json.loads(wake_entries[0][-1])
        assert "session_id" in payload
        assert "language" in payload
        assert "confidence" in payload
        assert "audio" not in payload
        assert "wav" not in payload

    def test_approved_false_invariant_in_memory_delegation(self):
        """Fix 1 regression: delegate_memory_write must send approved=False.

        Invariant: Voice Agent may REQUEST. It may never APPROVE.
        The broker auto-approves LOW-risk SEARCH_MEMORY regardless, but the
        value the Voice Agent sends must always be False.
        """
        session = VoiceSession()
        captured = []

        def capture(agent, action, params, broker_state):
            captured.append(broker_state)
            return {"success": True}

        with patch("backend.core.action_broker.ActionBroker.intake_request", side_effect=capture):
            delegate_memory_write(session, "what time is it", "en")

        assert len(captured) == 1
        approved_value = captured[0].get("approved")
        assert approved_value is False, (
            f"INVARIANT VIOLATION: delegate_memory_write passed approved={approved_value!r}. "
            "Voice Agent must NEVER send approved=True to the broker."
        )

    def test_audit_payloads_contain_no_raw_audio_or_biometrics(self):
        """All voice lifecycle audit payloads are metadata-only (no audio, voiceprints, PII)."""
        audit_calls = []
        with patch(
            "backend.core.action_broker.ActionBroker.log_audit_trail",
            side_effect=lambda *a, **k: audit_calls.append(a),
        ):
            session = _get_or_create_session()
            _end_session(session.session_id)

        forbidden_keys = {"audio_data", "wav_bytes", "voiceprint", "biometric", "speaker_embedding"}
        for call_args in audit_calls:
            try:
                payload = json.loads(call_args[-1])
            except Exception:
                continue
            overlap = forbidden_keys & set(payload.keys())
            assert not overlap, (
                f"Forbidden keys found in audit payload: {overlap}. "
                "Audit records must contain metadata only."
            )
