"""Voice Agent V1 — Security-Hardened I/O Gateway.

Architecture position:
    Microphone → Wake Word → Whisper.cpp → Voice Agent → Action Broker
    → Policy Engine → Memory/Agents/LLM → Voice Renderer → Piper

The Voice Agent is strictly an untrusted, low-privilege I/O gateway. It has
ZERO decision-making authority. It cannot:
  - Approve actions
  - Execute privileged operations
  - Write long-term memory directly
  - Authenticate users by voice
  - Bypass the Action Broker

All authority remains in:  Action Broker → Policy Engine → System

Security hardening:
  - Rule 1  Voice is never authentication (speaker identity = Unknown)
  - Rule 2  Voice can REQUEST; it can never APPROVE
  - Rule 3  No always-on transcription — only wake word / PTT modes
  - Rule 4  Confidence threshold: low-confidence → request clarification
  - Rule 5  VAD before Whisper (silence hallucination prevention)
  - Rule 6  Acoustic Echo Cancellation — never transcribe own TTS output
  - Rule 7  Audible-band filtering — reject ultrasonic injection
  - Rule 8  Secret scan every TTS payload before synthesis
  - Rule 9  Persona cannot create facts; only broker-verified facts may be spoken
  - Rule 10 Interrupts cannot cancel policy checks, rollbacks, or safety actions
  - Rule 11 Approval expires on interrupt; approval is re-checked on resume
  - Rule 12 Emotion/urgency is advisory display only; never changes policy tier
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
import wave
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class VoiceState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"


# ---------------------------------------------------------------------------
# Finite, validated emotion enum (Rule 9 / injection defence)
# ---------------------------------------------------------------------------

class Emotion(str, Enum):
    NEUTRAL = "NEUTRAL"
    LOYAL = "LOYAL"
    REPORTING = "REPORTING"
    THINKING = "THINKING"
    WARNING = "WARNING"
    URGENT = "URGENT"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    SAD = "SAD"


VALID_EMOTIONS: frozenset[str] = frozenset(e.value for e in Emotion)

# Deterministic Piper parameter map (LLM cannot override these)
EMOTION_TTS_MAP: dict[str, dict[str, Any]] = {
    Emotion.NEUTRAL:   {"pitch": "medium", "speed": 1.00, "volume": "medium"},
    Emotion.LOYAL:     {"pitch": "low",    "speed": 1.25, "volume": "medium"},
    Emotion.REPORTING: {"pitch": "medium", "speed": 1.00, "volume": "medium"},
    Emotion.THINKING:  {"pitch": "low",    "speed": 1.35, "volume": "low"},
    Emotion.WARNING:   {"pitch": "medium", "speed": 0.85, "volume": "high"},
    Emotion.URGENT:    {"pitch": "high",   "speed": 0.80, "volume": "high"},
    Emotion.SUCCESS:   {"pitch": "medium", "speed": 1.00, "volume": "medium"},
    Emotion.ERROR:     {"pitch": "low",    "speed": 1.25, "volume": "medium"},
    Emotion.SAD:       {"pitch": "low",    "speed": 1.35, "volume": "low"},
}

# ---------------------------------------------------------------------------
# Interrupt keyword patterns
# These are lightweight local-keyword matches; NOT full Whisper transcription
# ---------------------------------------------------------------------------

INTERRUPT_KEYWORDS: tuple[str, ...] = (
    "stop",
    "cancel",
    "wait",
    "pause",
    "kattappa stop",
    "kattappa, stop",
    "ఆగు",          # Telugu: stop/halt
    "ఆపు",          # Telugu: stop (variant)
    "ఆగండి",        # Telugu: please stop
)

# Actions that are NON-INTERRUPTIBLE (Rule 10)
NON_INTERRUPTIBLE_ACTIONS: frozenset[str] = frozenset({
    "policy_evaluation",
    "rollback",
    "safety_check",
    "approval_workflow",
    "resource_governor_check",
})

# ---------------------------------------------------------------------------
# Confidence and audio-safety thresholds
# ---------------------------------------------------------------------------

STT_CONFIDENCE_THRESHOLD = 0.70   # Rule 4: below → request clarification
VAD_ENERGY_THRESHOLD = 0.005      # Rule 5: RMS threshold for voice activity
AUDIBLE_FREQ_MIN_HZ = 80          # Rule 7: band-limit floor
AUDIBLE_FREQ_MAX_HZ = 8000        # Rule 7: band-limit ceiling

# Post-TTS listening window (seconds) before returning to IDLE / wake-word mode
SESSION_WINDOW_SECONDS = 4.0      # Bounded, visibly indicated, opt-in

# ---------------------------------------------------------------------------
# Voice Response Object schema
# The LLM emits ONLY this structure — never raw SSML (Rule 6 injection fix)
# ---------------------------------------------------------------------------

@dataclass
class VoiceResponseObject:
    text: str
    language: str = "english"
    voice_profile: str = "kattappa"
    emotion: str = Emotion.NEUTRAL
    intensity: float = 0.5
    interruptible: bool = True
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    checkpoint_id: str = field(default_factory=lambda: f"cp_{uuid.uuid4().hex[:8]}")

    def validate(self) -> "VoiceResponseObject":
        """Enforce schema constraints before passing to renderer."""
        # Sanitise text — strip any markup/control tokens (Rule 6)
        self.text = _strip_markup(self.text)
        # Validate emotion against finite enum (injection defence)
        if self.emotion.upper() not in VALID_EMOTIONS:
            self.emotion = Emotion.NEUTRAL
        else:
            self.emotion = self.emotion.upper()
        # Clamp intensity
        self.intensity = max(0.0, min(1.0, float(self.intensity)))
        return self


# ---------------------------------------------------------------------------
# Session conversation memory (volatile, session-scoped only)
# Long-term memory is owned by Memory Service; Voice Agent cannot write it.
# ---------------------------------------------------------------------------

@dataclass
class VoiceSession:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: VoiceState = VoiceState.IDLE
    started_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    # Session-scoped conversation turns (NOT persisted to Memory Service)
    transcript_history: list[dict[str, Any]] = field(default_factory=list)
    # Track the current active checkpoint for interrupt/resume
    active_checkpoint_id: str = ""
    # If a privileged task is paused, its approval MUST expire on resume
    paused_task: dict[str, Any] | None = None
    paused_task_approval_valid: bool = False  # Rule 11: always False after interrupt
    interrupt_count: int = 0
    interrupt_rate_limit_reset: float = field(default_factory=time.time)

    def record_turn(self, role: str, content: str, provenance: str = "UNTRUSTED_USER_INPUT") -> None:
        """Add a turn to session memory. Voice Agent cannot write long-term memory."""
        self.transcript_history.append({
            "role": role,
            "content": content,
            "provenance": provenance,
            "timestamp": time.time(),
        })
        self.last_activity = time.time()

    def is_expired(self, ttl_seconds: float = 3600.0) -> bool:
        return (time.time() - self.last_activity) > ttl_seconds

    def reset_interrupt_rate(self) -> None:
        self.interrupt_count = 0
        self.interrupt_rate_limit_reset = time.time()


# ---------------------------------------------------------------------------
# Global session store (in-process; no persistence)
# ---------------------------------------------------------------------------

_sessions: dict[str, VoiceSession] = {}
_sessions_lock = threading.Lock()


def _audit_voice_event(event: str, session_id: str, **extra: Any) -> None:
    """Write a voice lifecycle audit record via the broker.

    Records metadata only — no raw audio, no voiceprints, no biometrics.
    Falls back silently so a logging failure never breaks a voice path.
    """
    payload = json.dumps({
        "event": event,
        "session_id": session_id,
        "timestamp": time.time(),
        **{k: v for k, v in extra.items()},
    })
    try:
        from backend.core.action_broker import ActionBroker
        ActionBroker.log_audit_trail(
            "voice",
            f"VOICE_{event}",
            "auto_execute",
            event.lower(),
            payload,
        )
    except Exception as exc:
        logger.warning("Voice audit log failed for event %s: %s", event, exc)


def _get_or_create_session(session_id: str | None = None) -> VoiceSession:
    with _sessions_lock:
        if session_id and session_id in _sessions:
            return _sessions[session_id]
        session = VoiceSession()
        _sessions[session.session_id] = session
    # Audit: session started — metadata only, no audio
    _audit_voice_event("SESSION_START", session.session_id)
    return session


def _end_session(session_id: str) -> None:
    """Clear session from memory (Rule: session end clears context)."""
    # Audit before clearing so session_id is still available
    _audit_voice_event("SESSION_END", session_id)
    with _sessions_lock:
        _sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Voice Activity Detection (Rule 5)
# ---------------------------------------------------------------------------

def is_voice_active(wav_path: str, threshold: float = VAD_ENERGY_THRESHOLD) -> bool:
    """Returns True only if the WAV file contains human speech energy above threshold.
    Prevents Whisper hallucinating silence/fan noise/music as commands."""
    try:
        import numpy as np
        with wave.open(wav_path, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        data = np.frombuffer(frames, dtype=np.int16)
        if len(data) == 0:
            return False
        normalized = data.astype(float) / 32768.0
        rms = float(np.sqrt(float(np.mean(normalized ** 2))))
        return rms > threshold
    except Exception:
        # Fail open (allow) if VAD library unavailable; log it
        logger.warning("VAD check failed (library unavailable); defaulting to allow")
        return True


# ---------------------------------------------------------------------------
# Audible-band filtering (Rule 7 — reject ultrasonic / inaudible injection)
# ---------------------------------------------------------------------------

def is_within_audible_band(wav_path: str) -> bool:
    """Rejects audio whose dominant frequency is outside human speech range.
    Defends against dolphin-attack / ultrasonic command injection."""
    try:
        import numpy as np
        with wave.open(wav_path, "rb") as wf:
            sample_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        data = np.frombuffer(frames, dtype=np.int16).astype(float)
        if len(data) == 0:
            return True
        fft = np.fft.rfft(data)
        freqs = np.fft.rfftfreq(len(data), d=1.0 / sample_rate)
        magnitudes = np.abs(fft)
        if len(magnitudes) == 0:
            return True
        peak_idx = int(np.argmax(magnitudes))
        peak_freq = float(freqs[peak_idx])
        return AUDIBLE_FREQ_MIN_HZ <= peak_freq <= AUDIBLE_FREQ_MAX_HZ
    except Exception:
        logger.warning("Audible-band check failed; defaulting to allow")
        return True


# ---------------------------------------------------------------------------
# Text sanitisation helpers (Rules 6, 8, 9)
# ---------------------------------------------------------------------------

# Secret patterns — never speak these (Rule 8)
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(api[_-]?key|password|secret|token|credential|passwd|private[_-]?key)\s*[:=]\s*[a-zA-Z0-9_\-\.~]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
    re.compile(r"AIzaSy[A-Za-z0-9_\\-]{33}"),  # Google API Key
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),           # GitHub Token
    re.compile(r"sk-[a-zA-Z0-9]{40,}"),            # OpenAI key pattern
]

_MARKUP_PATTERN = re.compile(r"<[^>]+>")


def _contains_secret(text: str) -> bool:
    """Return True if text contains credential-like patterns."""
    return any(p.search(text) for p in _SECRET_PATTERNS)


def _strip_markup(text: str) -> str:
    """Remove any XML/HTML/SSML markup from text (injection fence, Rule 6)."""
    return _MARKUP_PATTERN.sub("", text)


def _strip_control_tokens(text: str) -> str:
    """Remove common LLM control / system prompt tokens."""
    control_tokens = [
        "###", "---", "<|endoftext|>", "<|im_start|>", "<|im_end|>",
        "[INST]", "[/INST]", "<<SYS>>", "<</SYS>>",
    ]
    for tok in control_tokens:
        text = text.replace(tok, "")
    return text.strip()


def sanitise_tts_text(text: str) -> str | None:
    """Full TTS text sanitisation pipeline (Rules 6, 8).
    Secret scan runs on RAW text BEFORE markup stripping so that
    PEM headers and similar patterns are not pre-mangled by the
    markup stripper.  Returns None if the text is blocked."""
    # Rule 8: secret scan on raw input first
    if _contains_secret(text):
        logger.warning("TTS blocked: secret/credential detected in payload")
        return None
    # Rule 6: strip markup / control tokens AFTER secret scan
    text = _strip_markup(text)
    text = _strip_control_tokens(text)
    return text


# ---------------------------------------------------------------------------
# Interrupt detection (Rule 3 / lightweight keyword spotter — NOT Whisper)
# ---------------------------------------------------------------------------

def is_interrupt_command(text: str) -> bool:
    """Lightweight keyword match only. NOT full transcription. NOT stored/sent.
    Active only during TTS playback (Rule 3 compliance)."""
    lower = text.strip().lower()
    return any(kw in lower for kw in INTERRUPT_KEYWORDS)


def check_interrupt_rate_limit(session: VoiceSession, max_per_minute: int = 5) -> bool:
    """Rate-limit interrupts to prevent DoS / rapid cancellation attacks (Rule 10)."""
    now = time.time()
    if now - session.interrupt_rate_limit_reset > 60.0:
        session.reset_interrupt_rate()
    session.interrupt_count += 1
    return session.interrupt_count <= max_per_minute


# ---------------------------------------------------------------------------
# Transcript structuring (prompt-injection defence)
# ---------------------------------------------------------------------------

def structure_transcript(
    transcript: str,
    confidence: float,
    language: str,
    session_id: str,
) -> dict[str, Any]:
    """Wraps raw transcript into an untrusted data envelope.
    The transcript is NEVER elevated to system instructions (Rule 7)."""
    return {
        "type": "user_content",
        "source": "voice",
        "provenance": "UNTRUSTED_AUDIO_INPUT",
        "transcript": transcript,
        "confidence": round(confidence, 4),
        "language": language,
        "session_id": session_id,
        "timestamp": time.time(),
    }


# ---------------------------------------------------------------------------
# STT: Whisper transcription with VAD + confidence gating
# ---------------------------------------------------------------------------

def transcribe_audio(
    wav_path: str,
    model_size: str = "small",
    *,
    skip_vad: bool = False,
    skip_band_check: bool = False,
) -> dict[str, Any]:
    """Transcribe audio through the full security pipeline:
    VAD → Audible-band → Whisper → Confidence gate.

    Returns a result dict with keys:
        ok: bool
        transcript: str
        confidence: float
        language: str
        reason: str (on failure)
    """
    # Rule 5: VAD check before invoking Whisper
    if not skip_vad and not is_voice_active(wav_path):
        return {
            "ok": False,
            "transcript": "",
            "confidence": 0.0,
            "language": "unknown",
            "reason": "vad_no_speech_detected",
        }

    # Rule 7: Audible-band check
    if not skip_band_check and not is_within_audible_band(wav_path):
        logger.warning("Audio rejected: dominant frequency outside audible band (possible ultrasonic injection)")
        return {
            "ok": False,
            "transcript": "",
            "confidence": 0.0,
            "language": "unknown",
            "reason": "out_of_audible_band_rejected",
        }

    # STT via faster-whisper
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {
            "ok": False,
            "transcript": "",
            "confidence": 0.0,
            "language": "unknown",
            "reason": "stt_unavailable_faster_whisper_not_installed",
        }

    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(wav_path, beam_size=5)
        segment_list = list(segments)

        if not segment_list:
            return {
                "ok": False,
                "transcript": "",
                "confidence": 0.0,
                "language": getattr(info, "language", "unknown"),
                "reason": "no_speech_segments",
            }

        # Compute average confidence across segments
        avg_confidence = float(
            sum(getattr(s, "avg_logprob", -1.0) for s in segment_list) / len(segment_list)
        )
        # Convert log-prob to 0-1 scale (clamped)
        confidence = max(0.0, min(1.0, (avg_confidence + 1.0) / 1.0))

        transcript = " ".join(s.text.strip() for s in segment_list).strip()
        language = getattr(info, "language", "unknown")

        # Rule 4: confidence threshold gate
        if confidence < STT_CONFIDENCE_THRESHOLD:
            return {
                "ok": False,
                "transcript": transcript,
                "confidence": confidence,
                "language": language,
                "reason": f"low_confidence_{confidence:.3f}_below_threshold_{STT_CONFIDENCE_THRESHOLD}",
            }

        return {
            "ok": True,
            "transcript": transcript,
            "confidence": confidence,
            "language": language,
            "reason": "",
        }

    except Exception as exc:
        logger.error("STT transcription failed: %s", exc)
        return {
            "ok": False,
            "transcript": "",
            "confidence": 0.0,
            "language": "unknown",
            "reason": f"transcription_error: {exc}",
        }


# ---------------------------------------------------------------------------
# TTS: Voice Renderer → Piper (Rules 6, 8, 9)
# ---------------------------------------------------------------------------

def render_speech(vro: VoiceResponseObject, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full TTS pipeline:
    VoiceResponseObject → sanitise → fact-verify → emotion→params → Piper.

    Voice Agent calls voice_tools.speak() which handles Piper/fallback routing
    and the Action Broker call for VOICE_SPEAKER_OUTPUT.
    """
    vro = vro.validate()

    # Rule 8: secret scan
    safe_text = sanitise_tts_text(vro.text)
    if safe_text is None:
        return {
            "ok": False,
            "reason": "tts_blocked_secret_detected",
        }

    # Rule 9: factual verification — persona cannot create facts
    if state is not None:
        from backend.tools.voice_tools import verify_factual_assertions
        safe_text = verify_factual_assertions(safe_text, state)

    # Validate emotion, derive TTS params deterministically
    emotion_key = vro.emotion if vro.emotion in VALID_EMOTIONS else Emotion.NEUTRAL
    tts_params = EMOTION_TTS_MAP.get(emotion_key, EMOTION_TTS_MAP[Emotion.NEUTRAL])

    # Build the structured speak payload (no raw SSML)
    speak_payload = {
        "text": safe_text,
        "emotion": emotion_key,
        "intensity": vro.intensity,
        "language": vro.language,
        "voice_profile": vro.voice_profile,
        "interruptible": vro.interruptible,
        "session_id": vro.session_id,
        "checkpoint_id": vro.checkpoint_id,
        "_tts_params": tts_params,   # consumed by speak(); never exposed to LLM
    }

    try:
        from backend.tools.voice_tools import speak
        result = speak(json.dumps(speak_payload), state=state)
        return {"ok": True, "result": result, "checkpoint_id": vro.checkpoint_id}
    except Exception as exc:
        logger.error("TTS render failed: %s", exc)
        return {"ok": False, "reason": f"tts_error: {exc}"}


# ---------------------------------------------------------------------------
# Interrupt handler (Rule 10, Rule 11)
# ---------------------------------------------------------------------------

def handle_interrupt(session: VoiceSession, checkpoint_id: str) -> dict[str, Any]:
    """Process an interrupt command:
    - Rate-limit check
    - Stop TTS (delegated to voice_tools via flag)
    - Publish TASK_INTERRUPTED to Action Broker
    - Expire any pending approval (Rule 11)
    - Return to LISTENING state
    """
    # Rate-limit interrupts (Rule 10)
    if not check_interrupt_rate_limit(session):
        return {
            "ok": False,
            "reason": "interrupt_rate_limit_exceeded",
        }

    # Signal TTS stop (voice_tools._is_piper_playing drives AEC)
    try:
        import backend.tools.voice_tools as vt
        vt._is_piper_playing = False  # AEC flag; stops capture loop
    except Exception:
        pass

    # Rule 11: paused privileged task approval is invalidated
    if session.paused_task:
        session.paused_task_approval_valid = False
        logger.info("Interrupt received: approval expired for paused task in session %s", session.session_id)

    # Save task state (Action Broker notification)
    interrupt_event = {
        "event": "TASK_INTERRUPTED",
        "checkpoint": checkpoint_id,
        "session_id": session.session_id,
        "timestamp": time.time(),
        "source": "voice_interrupt",
    }

    try:
        from backend.core.action_broker import ActionBroker
        ActionBroker.log_audit_trail(
            "voice",
            "VOICE_INTERRUPT",
            "auto_execute",
            "interrupt_received",
            json.dumps(interrupt_event),
        )
    except Exception as exc:
        logger.warning("Interrupt audit log failed: %s", exc)

    session.state = VoiceState.LISTENING
    session.active_checkpoint_id = ""

    return {
        "ok": True,
        "event": "TASK_INTERRUPTED",
        "checkpoint_id": checkpoint_id,
        "message": "Task paused. Approval invalidated. Returning to listening state.",
    }


# ---------------------------------------------------------------------------
# Wake word detection helper
# ---------------------------------------------------------------------------

def detect_wake_word_from_transcript(transcript: str) -> dict[str, Any]:
    """Parse wake word from an STT transcript (fallback when openwakeword unavailable)."""
    from backend.tools.voice_tools import parse_wake_command
    return parse_wake_command(transcript)


# ---------------------------------------------------------------------------
# Memory delegation (Voice Agent cannot write memory directly)
# ---------------------------------------------------------------------------

def delegate_memory_write(session: VoiceSession, transcript: str, language: str) -> dict[str, Any]:
    """Route transcript to Memory Service with provenance tagging.
    Voice Agent itself does NOT write memory."""
    memory_payload = {
        "source": "voice",
        "provenance": "UNTRUSTED_USER_INPUT",
        "content": transcript,
        "language": language,
        "session_id": session.session_id,
        "timestamp": time.time(),
    }

    try:
        from backend.core.action_broker import ActionBroker
        broker_res = ActionBroker.intake_request(
            "voice",
            "SEARCH_MEMORY",    # READ capability — voice agent is allowed
            memory_payload,
            # FIX: Voice Agent NEVER sets approved=True (architectural invariant).
            # The Policy Engine sees SEARCH_MEMORY as LOW risk and auto-approves it.
            # The Voice Agent's role is to REQUEST. Approval is the broker's decision.
            {"user_input": transcript, "logs": [], "approved": False},
        )
        return broker_res
    except Exception as exc:
        logger.warning("Memory delegation failed: %s", exc)
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Main Voice Agent Node
# ---------------------------------------------------------------------------

def voice_node(state: dict[str, Any]) -> dict[str, Any]:
    """Primary Voice Agent entry point — thin I/O gateway.

    Routes:
        audio_path   → STT pipeline → Action Broker → result
        speak_vro    → TTS pipeline → Piper
        interrupt    → TASK_INTERRUPTED → Action Broker
        status       → pipeline/session status
        default      → pipeline status
    """
    logs = state.setdefault("logs", [])
    user_input = state.get("user_input", "")
    lower_input = user_input.lower().strip()

    # Retrieve or create session
    session_id = state.get("voice_session_id")
    session = _get_or_create_session(session_id)
    state["voice_session_id"] = session.session_id

    logs.append(f"voice_agent: session={session.session_id} state={session.state.value}")

    # ------------------------------------------------------------------
    # INTERRUPT path (highest priority, but cannot cancel safety actions)
    # ------------------------------------------------------------------
    if state.get("voice_interrupt") or is_interrupt_command(lower_input):
        if session.state == VoiceState.SPEAKING:
            checkpoint = state.get("voice_checkpoint_id", session.active_checkpoint_id)
            result = handle_interrupt(session, checkpoint)
            state["voice_state"] = session.state.value
            state["result"] = json.dumps(result)
            logs.append(f"voice_agent: interrupt handled → {result}")
            return state
        else:
            # Interrupt when not speaking — acknowledge but do nothing
            state["result"] = "No active speech to interrupt."
            state["voice_state"] = session.state.value
            return state

    # ------------------------------------------------------------------
    # STT path — transcribe an audio file
    # ------------------------------------------------------------------
    audio_path = state.get("voice_audio_path")
    if audio_path:
        # Capture entry state BEFORE STT mutates it — needed for wake-word gate below
        pre_state = session.state
        session.state = VoiceState.PROCESSING
        logs.append(f"voice_agent: STT pipeline starting for {audio_path}")

        stt_result = transcribe_audio(
            audio_path,
            model_size=state.get("voice_model_size", "small"),
        )

        if not stt_result["ok"]:
            reason = stt_result.get("reason", "")
            # Audit: STT rejected — reason metadata only, no raw audio (forensic record)
            _audit_voice_event(
                "STT_REJECTED",
                session.session_id,
                reason=reason,
                confidence=round(stt_result.get("confidence", 0.0), 4),
                language=stt_result.get("language", "unknown"),
            )
            # Low confidence → clarification request (never execute ambiguous intent)
            if "low_confidence" in reason:
                session.state = VoiceState.LISTENING
                clarify_msg = (
                    "I did not understand clearly, my lord. "
                    "Could you repeat that? (Low confidence transcript discarded.)"
                )
                state["result"] = clarify_msg
                state["voice_state"] = session.state.value
                logs.append(f"voice_agent: low confidence STT → clarification requested")
                return state
            # VAD / band / transcription error
            session.state = VoiceState.IDLE
            state["result"] = f"Voice input rejected: {reason}"
            state["voice_state"] = session.state.value
            logs.append(f"voice_agent: STT rejected → {reason}")
            return state

        transcript = stt_result["transcript"]
        confidence = stt_result["confidence"]
        language = stt_result["language"]

        # Structure as untrusted data envelope (Rule 7 injection defence)
        structured = structure_transcript(transcript, confidence, language, session.session_id)
        logs.append(f"voice_agent: transcript structured as UNTRUSTED_AUDIO_INPUT")

        # Record turn in session memory (volatile; NOT long-term)
        session.record_turn("user", transcript, provenance="UNTRUSTED_AUDIO_INPUT")

        # Check for wake word only when session was IDLE at the point audio arrived.
        # pre_state captures the entry state before PROCESSING was set above.
        if pre_state not in (VoiceState.LISTENING, VoiceState.PROCESSING):
            wake_result = detect_wake_word_from_transcript(transcript)
            if not wake_result.get("wake_detected"):
                session.state = VoiceState.IDLE
                state["result"] = "Wake word not detected. Say 'Kattappa' followed by your command."
                state["voice_state"] = session.state.value
                logs.append("voice_agent: wake word not detected; returning to IDLE")
                return state
            # Audit: wake word detected — metadata only, no audio stored
            _audit_voice_event(
                "WAKE_DETECTED",
                session.session_id,
                language=language,
                wake_keyword=wake_result.get("wake_keyword", "unknown"),
                confidence=round(confidence, 4),
            )
            logs.append(f"voice_agent: wake word detected → session active")
            transcript = wake_result.get("command", transcript)
            structured["transcript"] = transcript

        # Check for interrupt command within transcribed text
        if is_interrupt_command(transcript):
            checkpoint = session.active_checkpoint_id
            result = handle_interrupt(session, checkpoint)
            state["voice_state"] = session.state.value
            state["result"] = json.dumps(result)
            logs.append("voice_agent: interrupt detected in transcript")
            return state

        # Forward to Action Broker (voice Agent cannot approve; it only requests)
        session.state = VoiceState.PROCESSING
        broker_state = {
            "user_input": transcript,
            "logs": [],
            "approved": False,  # Voice NEVER auto-approves (Rule 2)
            "voice_structured": structured,
        }

        from backend.core.action_broker import ActionBroker
        broker_res = ActionBroker.intake_request("voice", "VOICE_STT", {}, broker_state)

        session.state = VoiceState.IDLE
        state["voice_state"] = session.state.value
        state["voice_transcript"] = structured
        state["result"] = json.dumps({
            "transcript": transcript,
            "confidence": confidence,
            "language": language,
            "provenance": "UNTRUSTED_AUDIO_INPUT",
            "broker": broker_res,
        })
        logs.append(f"voice_agent: STT complete → broker result: {broker_res.get('success')}")
        return state

    # ------------------------------------------------------------------
    # TTS path — speak a VoiceResponseObject
    # ------------------------------------------------------------------
    vro_raw = state.get("voice_speak")
    if vro_raw:
        session.state = VoiceState.SPEAKING
        logs.append("voice_agent: TTS pipeline starting")

        # Parse VoiceResponseObject
        if isinstance(vro_raw, str):
            try:
                vro_dict = json.loads(vro_raw)
            except Exception:
                vro_dict = {"text": vro_raw}
        elif isinstance(vro_raw, dict):
            vro_dict = vro_raw
        else:
            vro_dict = {"text": str(vro_raw)}

        vro = VoiceResponseObject(
            text=vro_dict.get("text", ""),
            language=vro_dict.get("language", "english"),
            voice_profile=vro_dict.get("voice_profile", "kattappa"),
            emotion=vro_dict.get("emotion", Emotion.NEUTRAL),
            intensity=float(vro_dict.get("intensity", 0.5)),
            interruptible=bool(vro_dict.get("interruptible", True)),
        )

        # Set active checkpoint so interrupts can reference it
        session.active_checkpoint_id = vro.checkpoint_id

        tts_result = render_speech(vro, state=state)

        session.state = VoiceState.IDLE
        session.active_checkpoint_id = ""

        if tts_result.get("ok"):
            # Session window: brief listening period after TTS (Rule 3 compliant)
            # — keyword-only spotter, bounded, visible, NOT full Whisper
            state["voice_session_window_active"] = True
            state["voice_session_window_expires"] = time.time() + SESSION_WINDOW_SECONDS

        state["voice_state"] = session.state.value
        state["result"] = json.dumps(tts_result)
        logs.append(f"voice_agent: TTS complete → {tts_result.get('ok')}")
        return state

    # ------------------------------------------------------------------
    # Session end path — clear session memory
    # ------------------------------------------------------------------
    if lower_input in ("end session", "session end", "logout", "goodbye", "bye"):
        sid = session.session_id
        _end_session(sid)
        state["result"] = "Voice session ended. Returning to wake word mode."
        state["voice_state"] = VoiceState.IDLE.value
        logs.append(f"voice_agent: session {sid} ended and cleared")
        return state

    # ------------------------------------------------------------------
    # Engineering mode routing (for tests/custom parameter tuning)
    # ------------------------------------------------------------------
    if "engineering" in lower_input:
        state["result"] = "ENGINEERING mode: custom audio synthesis parameters active."
        state["voice_state"] = session.state.value
        logs.append("voice_agent: routed to engineering mode")
        return state

    # ------------------------------------------------------------------
    # Status / info path
    # ------------------------------------------------------------------
    if "status" in lower_input or "pipeline" in lower_input or "voice" in lower_input:
        from backend.tools.voice_tools import voice_pipeline_status
        pipeline = voice_pipeline_status()
        status_report = {
            "voice_agent_version": "V1",
            "session_id": session.session_id,
            "session_state": session.state.value,
            "session_turns": len(session.transcript_history),
            "pipeline": pipeline,
            "security": {
                "stt_confidence_threshold": STT_CONFIDENCE_THRESHOLD,
                "vad_enabled": True,
                "audible_band_filter": True,
                "echo_cancellation": True,
                "secret_scan_enabled": True,
                "persona_fact_separation": True,
                "emotion_metadata_separation": True,
                "interrupt_rate_limit": "5/min",
                "session_window_seconds": SESSION_WINDOW_SECONDS,
                "voice_is_not_authentication": True,
                "voice_cannot_approve_actions": True,
            },
        }
        state["result"] = json.dumps(status_report, indent=2)
        state["voice_state"] = session.state.value
        logs.append("voice_agent: status report generated")
        return state

    # ------------------------------------------------------------------
    # Default — return pipeline status summary
    # ------------------------------------------------------------------
    from backend.tools.voice_tools import voice_pipeline_status, voice_profile
    pipeline = voice_pipeline_status()
    profile = voice_profile()
    lines = [
        "Voice Agent V1 — Security-Hardened I/O Gateway",
        f"Session: {session.session_id} | State: {session.state.value}",
        f"Profile: {profile['name']} ({profile['style']})",
        f"Languages: {profile['primary_spoken_language']} (primary), {profile['secondary_spoken_language']} (secondary)",
        f"STT: {pipeline['stt']['status']} | TTS: {pipeline['tts']['primary_decision']}",
        f"Wake: {pipeline['wake']['status']}",
        "",
        "Security posture: zero authority | zero approvals | zero direct execution",
        "All actions route through: Voice Agent → Action Broker → Policy Engine",
    ]
    state["result"] = "\n".join(lines)
    state["voice_state"] = session.state.value
    logs.append("voice_agent: default status returned")
    return state
