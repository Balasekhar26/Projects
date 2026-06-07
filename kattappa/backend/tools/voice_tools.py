from __future__ import annotations

import base64
import importlib.util
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path


WAKE_NAMES = ("kattappa", "mama", "kittu")

KATTAPPA_VOICE_PROFILE = {
    "id": "kattappa_original_loyal_warrior",
    "name": "Kattappa Original Loyal Warrior",
    "style": "deep, calm, authoritative, warm, and cinematic",
    "rate": 145,
    "volume": 0.95,
    "pitch": 42,
    "primary_spoken_language": "Telugu",
    "secondary_spoken_language": "English",
    "text_output_language": "English",
    "policy": (
        "Original assistant voice profile only. It must not clone, imitate, or claim to be "
        "any movie character, actor, or identifiable person's voice."
    ),
}


def speak(text: str) -> str:
    try:
        import pyttsx3
    except Exception as exc:
        return _speak_with_os_adapter(text, exc)
    try:
        engine = pyttsx3.init()
        _apply_kattappa_profile(engine)
        engine.say(text)
        engine.runAndWait()
        return "spoken via pyttsx3 using Kattappa original voice profile"
    except Exception as exc:
        return _speak_with_os_adapter(text, exc)


def voice_profile() -> dict[str, object]:
    return dict(KATTAPPA_VOICE_PROFILE)


def voice_pipeline_status() -> dict[str, object]:
    wake_installed = _module_available("openwakeword")
    custom_wake_models = _custom_wake_models()
    stt_installed = _module_available("faster_whisper")
    piper_installed = _module_available("piper") or shutil.which("piper") is not None
    pyttsx3_installed = _module_available("pyttsx3")
    native_tts = _native_tts_adapter()
    return {
        "mode": "local_backend_voice_pipeline",
        "primary_path": "desktop_audio_to_backend",
        "browser_speech_primary": False,
        "wake_names": list(WAKE_NAMES),
        "wake": {
            "engine": "openwakeword",
            "installed": wake_installed,
            "custom_models": [str(path) for path in custom_wake_models],
            "custom_models_configured": bool(custom_wake_models),
            "primary_decision": (
                "openwakeword_custom_models"
                if wake_installed and custom_wake_models
                else "local_stt_wake_name_parser"
            ),
            "status": (
                "ready_with_custom_models"
                if wake_installed and custom_wake_models
                else "fallback_to_transcribed_wake_names"
            ),
        },
        "stt": {
            "engine": "faster-whisper",
            "installed": stt_installed,
            "status": "installed" if stt_installed else "missing",
        },
        "tts": {
            "preferred_engine": "piper",
            "piper_installed": piper_installed,
            "active_fallback": "pyttsx3" if pyttsx3_installed else native_tts,
            "available": piper_installed or pyttsx3_installed or native_tts != "",
        },
        "profile": voice_profile(),
        "safe_fallback": (
            "Typed chat remains available. Speech output falls back to pyttsx3 or native OS speech. "
            "Wake detection falls back to local STT wake-name parsing when openWakeWord is unavailable."
        ),
    }


def transcribe_file(path: str, model_size: str = "small") -> str:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        return f"Speech-to-text is unavailable on this OS/session: {exc}"
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(Path(path)))
    return " ".join(segment.text.strip() for segment in segments).strip()


def process_voice_audio(audio_base64: str, mime_type: str = "audio/webm", model_size: str = "small") -> dict[str, object]:
    status = voice_pipeline_status()
    try:
        audio_bytes = base64.b64decode(audio_base64, validate=True)
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"invalid_audio_payload: {exc}",
            "pipeline": status,
            "transcript": "",
            "wake_detected": False,
            "wake_name": "",
            "command": "",
        }
    if not audio_bytes:
        return {
            "ok": False,
            "reason": "empty_audio_payload",
            "pipeline": status,
            "transcript": "",
            "wake_detected": False,
            "wake_name": "",
            "command": "",
        }

    suffix = _audio_suffix(mime_type)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(audio_bytes)
        audio_path = handle.name
    try:
        transcript = transcribe_file(audio_path, model_size=model_size)
    finally:
        Path(audio_path).unlink(missing_ok=True)
    parsed = parse_wake_command(transcript)
    return {
        "ok": not transcript.startswith("Speech-to-text is unavailable"),
        "reason": "" if parsed["wake_detected"] else "wake_name_not_detected",
        "pipeline": status,
        "transcript": transcript,
        **parsed,
    }


def parse_wake_command(transcript: str) -> dict[str, object]:
    normalized = " ".join(transcript.strip().split())
    lower = normalized.lower()
    for wake_name in WAKE_NAMES:
        index = lower.find(wake_name)
        if index == -1:
            continue
        command = normalized[index + len(wake_name) :].strip(" ,:;-")
        return {
            "wake_detected": True,
            "wake_name": wake_name,
            "command": command,
        }
    return {
        "wake_detected": False,
        "wake_name": "",
        "command": "",
    }


def _speak_with_os_adapter(text: str, cause: Exception) -> str:
    system = platform.system().lower()
    if system == "darwin" and shutil.which("say"):
        subprocess.Popen(["say", "-r", str(KATTAPPA_VOICE_PROFILE["rate"]), text])
        return "spoken via macOS say using Kattappa original voice profile"
    if system == "linux":
        if shutil.which("espeak"):
            subprocess.Popen(
                [
                    "espeak",
                    "-s",
                    str(KATTAPPA_VOICE_PROFILE["rate"]),
                    "-p",
                    str(KATTAPPA_VOICE_PROFILE["pitch"]),
                    text,
                ]
            )
            return "spoken via espeak using Kattappa original voice profile"
        if shutil.which("spd-say"):
            subprocess.Popen(["spd-say", "-r", "-25", text])
            return "spoken via spd-say using Kattappa original voice profile"
    if system == "windows" and shutil.which("powershell"):
        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$synth.Rate = -2; "
            "$synth.Volume = 95; "
            "$synth.Speak($args[0])"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", command, text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return "spoken via Windows speech using Kattappa original voice profile"
    return f"Speech output is unavailable on this OS/session: {cause}"


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _native_tts_adapter() -> str:
    system = platform.system().lower()
    if system == "darwin" and shutil.which("say"):
        return "macOS say"
    if system == "linux":
        if shutil.which("espeak"):
            return "espeak"
        if shutil.which("spd-say"):
            return "spd-say"
    if system == "windows" and shutil.which("powershell"):
        return "Windows speech"
    return ""


def _custom_wake_models() -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    model_dir = root / "voice" / "wakewords"
    if not model_dir.exists():
        return []
    return sorted(model_dir.glob("*.tflite")) + sorted(model_dir.glob("*.onnx"))


def _audio_suffix(mime_type: str) -> str:
    lowered = mime_type.lower()
    if "wav" in lowered:
        return ".wav"
    if "mpeg" in lowered or "mp3" in lowered:
        return ".mp3"
    if "ogg" in lowered:
        return ".ogg"
    if "mp4" in lowered:
        return ".mp4"
    return ".webm"


def _apply_kattappa_profile(engine: object) -> None:
    try:
        engine.setProperty("rate", KATTAPPA_VOICE_PROFILE["rate"])
        engine.setProperty("volume", KATTAPPA_VOICE_PROFILE["volume"])
    except Exception:
        return
    try:
        voices = engine.getProperty("voices") or []
    except Exception:
        return
    preferred_terms = ("male", "david", "mark", "ravi", "english", "india")
    for voice in voices:
        label = f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')}".lower()
        if any(term in label for term in preferred_terms):
            try:
                engine.setProperty("voice", voice.id)
            except Exception:
                pass
            break
