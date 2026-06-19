from __future__ import annotations

import base64
import importlib.util
import os
import platform
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any


WAKE_NAMES = ("kattappa", "mama", "kittu")
WAKE_SAMPLE_RATE = 16000
WAKE_CHUNK_SAMPLES = 1280
WAKE_THRESHOLD = 0.5

KATTAPPA_LANGUAGE_CONTRACT = {
    "primary_spoken_language": "Telugu",
    "secondary_spoken_language": "English",
    "text_output_language": "English",
    "voice_prompt_policy": "Spoken voice prompts are Telugu-first with English support.",
    "assistant_response_policy": (
        "Typed assistant responses stay English-only; assistant response speech is rendered in Telugu "
        "through a local-model translator when available, with a Telugu fallback summary when not available."
    ),
}

KATTAPPA_VOICE_PROFILE = {
    "id": "kattappa_original_loyal_warrior",
    "name": "Kattappa Original Loyal Warrior",
    "style": "deep, authoritative, booming, loyal, and dramatic (Telugu Movie Profile)",
    "rate": 125,
    "volume": 1.0,
    "pitch": 35,
    "primary_spoken_language": KATTAPPA_LANGUAGE_CONTRACT["primary_spoken_language"],
    "secondary_spoken_language": KATTAPPA_LANGUAGE_CONTRACT["secondary_spoken_language"],
    "text_output_language": KATTAPPA_LANGUAGE_CONTRACT["text_output_language"],
    "policy": (
        "Inspired by the loyal Telugu warrior Kattappa from the Bahubali cinematic universe. "
        "Speaks with a slow, booming, and authoritative tone. It must not clone, imitate, or claim "
        "to be any movie character, actor, or identifiable person's voice."
    ),
}

KATTAPPA_SPOKEN_PROMPTS = {
    "wake_prompt": "వింటున్నాను. Say Kattappa, Mama, or Kittu, then your command.",
    "wake_ack": "చెప్పండి. I am listening.",
    "command_ack": "సరే. Okay.",
}

TELUGU_SPEECH_PHRASES = {
    "hi": "హాయ్.",
    "hello": "హలో.",
    "hey": "హే.",
    "okay": "సరే.",
    "i am ready.": "నేను సిద్ధంగా ఉన్నాను.",
    "ready": "సిద్ధంగా ఉన్నాను.",
    "i can help.": "నేను సహాయం చేయగలను.",
    "no response returned.": "సమాధానం రాలేదు.",
    "the approved task completed.": "ఆమోదించిన పని పూర్తయింది.",
    "approval needed. approve to continue.": "అనుమతి అవసరం. మీరు ఆమోదించిన తర్వాత పని కొనసాగుతుంది.",
    "kattappa ai os is running locally.": "కట్టప్ప ఏఐ ఓఎస్ ఈ కంప్యూటర్‌లో నడుస్తోంది.",
    "hi, kattappa ai os is online and ready.": "హాయ్. కట్టప్ప ఏఐ ఓఎస్ ఆన్‌లైన్‌లో ఉంది, సిద్ధంగా ఉంది.",
    "hello, kattappa ai os is online and ready.": "హలో. కట్టప్ప ఏఐ ఓఎస్ ఆన్‌లైన్‌లో ఉంది, సిద్ధంగా ఉంది.",
    "hey, kattappa ai os is online and ready.": "హే. కట్టప్ప ఏఐ ఓఎస్ ఆన్‌లైన్‌లో ఉంది, సిద్ధంగా ఉంది.",
}


def speak(text: str, purpose: str = "assistant_response") -> str:
    spoken_text = normalize_spoken_text(text, purpose=purpose)
    if not spoken_text:
        return "Speech output skipped: empty text"
    piper_result = _speak_with_piper(spoken_text)
    if piper_result:
        return piper_result
    try:
        import pyttsx3
    except Exception as exc:
        return _speak_with_os_adapter(spoken_text, exc)
    try:
        engine = pyttsx3.init()
        _apply_kattappa_profile(engine)
        engine.say(spoken_text)
        engine.runAndWait()
        return "spoken via pyttsx3 using Kattappa original voice profile"
    except Exception as exc:
        return _speak_with_os_adapter(spoken_text, exc)


def voice_profile() -> dict[str, object]:
    return dict(KATTAPPA_VOICE_PROFILE)


def voice_language_contract() -> dict[str, object]:
    return dict(KATTAPPA_LANGUAGE_CONTRACT)


def normalize_spoken_text(text: str, purpose: str = "assistant_response") -> str:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return ""
    if purpose in KATTAPPA_SPOKEN_PROMPTS:
        return KATTAPPA_SPOKEN_PROMPTS[purpose]
    if purpose == "assistant_response":
        return render_assistant_reply_for_telugu_speech(cleaned)
    return cleaned


def render_assistant_reply_for_telugu_speech(text: str) -> str:
    cleaned = _speech_safe_text(text)
    if not cleaned:
        return ""
    if _contains_telugu(cleaned):
        return cleaned
    phrase = _telugu_phrase(cleaned)
    if phrase:
        return phrase
    translated = _translate_to_telugu_with_local_model(cleaned)
    if translated:
        return translated
    return _telugu_fallback_summary(cleaned)


def voice_pipeline_status() -> dict[str, object]:
    wake_installed = _module_available("openwakeword")
    custom_wake_models = _custom_wake_models()
    stt_installed = _module_available("faster_whisper")
    piper_installed = _piper_installed()
    piper_command = shutil.which("piper")
    piper_model = _piper_voice_model()
    pyttsx3_installed = _module_available("pyttsx3")
    native_tts = _native_tts_adapter()
    openwakeword_ready = wake_installed and bool(custom_wake_models)
    piper_ready = piper_command is not None and piper_model is not None
    return {
        "mode": "local_backend_voice_pipeline",
        "primary_path": "desktop_microphone_to_backend_openwakeword_stt_tts",
        "browser_speech_primary": False,
        "wake_names": list(WAKE_NAMES),
        "wake": {
            "engine": "openwakeword",
            "installed": wake_installed,
            "custom_models": [str(path) for path in custom_wake_models],
            "custom_models_configured": bool(custom_wake_models),
            "threshold": WAKE_THRESHOLD,
            "fallback_engine": "local_stt_wake_name_parser",
            "primary_decision": (
                "openwakeword_custom_models"
                if openwakeword_ready
                else "local_stt_wake_name_parser"
            ),
            "status": (
                "ready_with_custom_models"
                if openwakeword_ready
                else "fallback_to_transcribed_wake_names"
            ),
        },
        "stt": {
            "engine": "faster-whisper",
            "installed": stt_installed,
            "status": "installed" if stt_installed else "missing",
            "fallback": "typed_chat",
        },
        "tts": {
            "preferred_engine": "piper",
            "piper_installed": piper_installed,
            "piper_command": piper_command or "",
            "piper_model": str(piper_model) if piper_model else "",
            "piper_model_configured": piper_model is not None,
            "primary_decision": "piper_local_model" if piper_ready else "pyttsx3_or_native_os",
            "active_fallback": "pyttsx3" if pyttsx3_installed else native_tts,
            "available": piper_ready or pyttsx3_installed or native_tts != "",
            "assistant_response_language": "Telugu",
            "translation_path": "local_ollama_telugu_renderer_with_phrase_fallback",
        },
        "profile": voice_profile(),
        "language_contract": voice_language_contract(),
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
        wake_result = detect_wake_word(audio_path, mime_type=mime_type)
        transcript = transcribe_file(audio_path, model_size=model_size)
    finally:
        Path(audio_path).unlink(missing_ok=True)
    stt_unavailable = transcript.startswith("Speech-to-text is unavailable")
    parsed = parse_wake_command(transcript) if not stt_unavailable else _empty_wake_parse()
    if wake_result["detected"] and not parsed["wake_detected"]:
        parsed = {
            "wake_detected": True,
            "wake_name": wake_result["wake_name"],
            "command": _command_from_openwakeword_transcript(transcript),
        }
    wake_engine = (
        "openwakeword"
        if wake_result["detected"]
        else "local_stt_wake_name_parser"
        if parsed["wake_detected"]
        else ""
    )
    return {
        "ok": not stt_unavailable,
        "reason": "stt_unavailable" if stt_unavailable else "" if parsed["wake_detected"] else "wake_name_not_detected",
        "pipeline": status,
        "transcript": transcript,
        "wake_engine": wake_engine,
        "wake_result": wake_result,
        **parsed,
    }


def detect_wake_word(path: str, mime_type: str = "audio/webm") -> dict[str, object]:
    result = _empty_wake_result()
    custom_wake_models = _custom_wake_models()
    if not _module_available("openwakeword"):
        result["reason"] = "openwakeword_not_installed"
        return result
    if not custom_wake_models:
        result["reason"] = "custom_wake_models_not_configured"
        return result
    audio, audio_reason = _load_openwakeword_audio(path, mime_type=mime_type)
    if audio is None:
        result["reason"] = audio_reason
        return result
    try:
        from openwakeword.model import Model
    except Exception as exc:
        result["reason"] = f"openwakeword_unavailable: {exc}"
        return result
    try:
        model = Model(wakeword_models=[str(model_path) for model_path in custom_wake_models])
        scores = _score_openwakeword_audio(model, audio)
    except Exception as exc:
        result["reason"] = f"openwakeword_detection_failed: {exc}"
        return result
    if not scores:
        result["used"] = True
        result["reason"] = "openwakeword_returned_no_scores"
        return result
    model_name, score = max(scores.items(), key=lambda item: item[1])
    result.update(
        {
            "used": True,
            "detected": score >= WAKE_THRESHOLD,
            "wake_name": _wake_name_from_model_name(model_name) if score >= WAKE_THRESHOLD else "",
            "score": score,
            "scores": scores,
            "reason": "" if score >= WAKE_THRESHOLD else "wake_threshold_not_met",
        }
    )
    return result


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


def _empty_wake_parse() -> dict[str, object]:
    return {
        "wake_detected": False,
        "wake_name": "",
        "command": "",
    }


def _empty_wake_result() -> dict[str, object]:
    return {
        "engine": "openwakeword",
        "used": False,
        "detected": False,
        "wake_name": "",
        "score": 0.0,
        "scores": {},
        "threshold": WAKE_THRESHOLD,
        "reason": "",
    }


def _command_from_openwakeword_transcript(transcript: str) -> str:
    normalized = " ".join(transcript.strip().split())
    if normalized.lower() in WAKE_NAMES:
        return ""
    return normalized


def _speak_with_os_adapter(text: str, cause: Exception) -> str:
    system = platform.system().lower()
    if system == "darwin":
        if shutil.which("say"):
            subprocess.Popen(["say", "-r", "125", text])
            return "spoken via macOS say using Kattappa cinematic movie voice profile"
        if shutil.which("osascript"):
            try:
                safe_text = text.replace('"', '\\"')
                subprocess.Popen(["osascript", "-e", f'say "{safe_text}"'])
                return "spoken via macOS AppleScript fallback using Kattappa cinematic movie voice profile"
            except Exception:
                pass

    if system == "linux":
        if shutil.which("espeak"):
            subprocess.Popen(
                [
                    "espeak",
                    "-v",
                    "te",
                    "-s",
                    "125",
                    "-p",
                    "35",
                    text,
                ]
            )
            return "spoken via espeak using Kattappa cinematic movie voice profile"
        if shutil.which("spd-say"):
            subprocess.Popen(["spd-say", "-l", "te", "-r", "-35", text])
            return "spoken via spd-say using Kattappa cinematic movie voice profile"
        if shutil.which("flite"):
            subprocess.Popen(["flite", "-t", text])
            return "spoken via Linux flite using Kattappa cinematic movie voice profile"
        if shutil.which("festival"):
            try:
                proc = subprocess.Popen(["festival", "--tts"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                proc.communicate(input=text.encode("utf-8"))
                return "spoken via Linux festival using Kattappa cinematic movie voice profile"
            except Exception:
                pass

    if system == "windows":
        if shutil.which("powershell"):
            command = (
                "Add-Type -AssemblyName System.Speech; "
                "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$synth.Rate = -3; "
                "$synth.Volume = 100; "
                "$voice = $synth.GetInstalledVoices() | Where-Object { "
                "  $_.VoiceInfo.Language.Name -like '*te*' -or "
                "  $_.VoiceInfo.Name -like '*Heera*' -or "
                "  $_.VoiceInfo.Name -like '*Ravi*' -or "
                "  $_.VoiceInfo.Name -like '*Hemant*' -or "
                "  $_.VoiceInfo.Language.Name -like '*in*' "
                "} | Select-Object -First 1; "
                "if ($voice) { $synth.SelectVoice($voice.VoiceInfo.Name); } "
                "$synth.Speak($args[0])"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", command, text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return "spoken via Windows speech using Kattappa cinematic movie voice profile"
        elif shutil.which("cscript") or shutil.which("cscript.exe"):
            try:
                import tempfile
                safe_text = text.replace('"', '""')
                vbs_code = (
                    f'Set Speech = CreateObject("SAPI.SpVoice")\n'
                    f'Speech.Rate = -3\n'
                    f'Speech.Volume = 100\n'
                    f'Speech.Speak "{safe_text}"\n'
                )
                with tempfile.NamedTemporaryFile(delete=False, suffix=".vbs", mode="w", encoding="utf-8") as f:
                    f.write(vbs_code)
                    vbs_path = f.name
                subprocess.Popen(["cscript.exe", "//NoLogo", vbs_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return "spoken via Windows VBScript fallback using Kattappa cinematic movie voice profile"
            except Exception:
                pass
    return f"Speech output is unavailable on this OS/session: {cause}"


def _speak_with_piper(text: str) -> str | None:
    piper_command = shutil.which("piper")
    piper_model = _piper_voice_model()
    if not piper_command or not piper_model:
        return None
    output_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
            output_path = handle.name
        process = subprocess.run(
            [piper_command, "--model", str(piper_model), "--output_file", output_path],
            env=_piper_process_env(),
            input=text,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        if process.returncode != 0:
            return None
        if not _play_wav(output_path):
            return None
        return "spoken via Piper local TTS using Kattappa original voice profile"
    except Exception:
        return None
    finally:
        if output_path:
            Path(output_path).unlink(missing_ok=True)


def _piper_process_env() -> dict[str, str]:
    env = os.environ.copy()
    if env.get("ESPEAK_DATA_PATH"):
        return env
    for candidate in (
        Path("/opt/homebrew/share/espeak-ng-data"),
        Path("/opt/homebrew/opt/espeak-ng/share/espeak-ng-data"),
        Path("/usr/local/share/espeak-ng-data"),
        Path("/usr/local/opt/espeak-ng/share/espeak-ng-data"),
        Path("/usr/share/espeak-ng-data"),
    ):
        if (candidate / "phontab").exists():
            env["ESPEAK_DATA_PATH"] = str(candidate)
            break
    return env


def _play_wav(path: str) -> bool:
    system = platform.system().lower()
    if system == "darwin" and shutil.which("afplay"):
        subprocess.run(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return True
    if system == "linux":
        if shutil.which("aplay"):
            subprocess.run(["aplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return True
        if shutil.which("paplay"):
            subprocess.run(["paplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return True
    if system == "windows" and shutil.which("powershell"):
        command = (
            "Add-Type -AssemblyName System.Media; "
            "$player = New-Object System.Media.SoundPlayer($args[0]); "
            "$player.PlaySync()"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", command, path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return True
    return False


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _piper_installed() -> bool:
    return _module_available("piper") or shutil.which("piper") is not None


def _piper_voice_model() -> Path | None:
    root = Path(__file__).resolve().parents[2]
    search_roots = [
        root / "voice" / "tts",
        root / "models" / "voice",
        root / "models" / "piper",
    ]
    for search_root in search_roots:
        if not search_root.exists():
            continue
        models = sorted(path for path in search_root.glob("*.onnx") if path.is_file())
        if models:
            return models[0]
    return None


def _speech_safe_text(text: str) -> str:
    if "```" in text or re.search(r"(?m)^\s{0,4}(def|class|function|const|let|var|import|from)\s+", text):
        return (
            "This reply contains code or technical steps. I prepared the full English answer in chat, "
            "and I can explain any part if you ask."
        )
    without_links = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    without_markdown = re.sub(r"[*_`#>]+", "", without_links)
    compact = " ".join(without_markdown.split())
    max_chars = 1400
    if len(compact) > max_chars:
        compact = f"{compact[:max_chars].rsplit(' ', 1)[0]}. The rest is available in chat."
    return compact


def _telugu_phrase(text: str) -> str:
    key = text.strip().lower()
    if key in TELUGU_SPEECH_PHRASES:
        return TELUGU_SPEECH_PHRASES[key]
    if "backend is offline" in key:
        return "బ్యాక్ ఎండ్ ఆఫ్‌లైన్‌లో ఉంది. కట్టప్పను ప్రారంభించి మళ్లీ పంపండి."
    if "connection dropped" in key:
        return "కనెక్షన్ ఆగిపోయింది. మీరు మళ్లీ పంపవచ్చు."
    if "approval needed" in key:
        return "అనుమతి అవసరం. మీరు ఆమోదించిన తర్వాత పని కొనసాగుతుంది."
    if key in {"done", "completed", "finished"} or "completed" in key:
        return "పని పూర్తయింది."
    if "voice unavailable" in key:
        return "వాయిస్ ప్రస్తుతం అందుబాటులో లేదు. మీరు సందేశం టైప్ చేయవచ్చు."
    if "wake name needed" in key:
        return "ముందుగా కట్టప్ప, మామా, లేదా కిట్టు అని పిలవండి."
    if "working" in key or "processing" in key:
        return "పని జరుగుతోంది."
    return ""


def _translate_to_telugu_with_local_model(text: str) -> str:
    if os.getenv("KATTAPPA_VOICE_TRANSLATE_LOCAL_MODEL", "true").lower() in {"0", "false", "no", "off"}:
        return ""
    try:
        import httpx
        from backend.core.config import load_config
    except Exception:
        return ""
    config = load_config()
    model = os.getenv("KATTAPPA_VOICE_TRANSLATE_MODEL", config.model_map.get("fast", config.model_map["general"]))
    prompt = (
        "Translate this assistant reply into natural spoken Telugu for text-to-speech. "
        "Keep product names, file names, commands, and code keywords in English only when needed. "
        "Return only Telugu script text, no markdown, no explanation, no quotation marks.\n\n"
        f"English reply:\n{text}"
    )
    try:
        response = httpx.post(
            f"{config.ollama_host}/api/chat",
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You render Kattappa AI OS voice replies in Telugu. "
                            "The visual chat remains English, but spoken output must be Telugu."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"num_predict": 260, "temperature": 0.1},
            },
            timeout=float(os.getenv("KATTAPPA_VOICE_TRANSLATE_TIMEOUT", "18")),
        )
        response.raise_for_status()
        translated = response.json().get("message", {}).get("content", "").strip()
    except Exception:
        return ""
    translated = _clean_translated_telugu(translated)
    return translated if _contains_telugu(translated) else ""


def _clean_translated_telugu(text: str) -> str:
    cleaned = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"[*_`#>]+", "", cleaned)
    cleaned = cleaned.strip().strip('"').strip("'")
    return " ".join(cleaned.split())


def _telugu_fallback_summary(text: str) -> str:
    key = text.lower()
    if "code" in key or "technical" in key:
        return "నేను పూర్తి సాంకేతిక సమాధానాన్ని చాట్‌లో సిద్ధం చేశాను. ఏ భాగం కావాలో అడిగితే తెలుగులో వివరించగలను."
    if "approval" in key:
        return "ఈ పనికి అనుమతి అవసరం. మీరు ఆమోదించిన తర్వాత నేను కొనసాగుతాను."
    return "సమాధానం సిద్ధంగా ఉంది. పూర్తి ఇంగ్లీష్ వివరాలు చాట్‌లో ఉన్నాయి. మీరు అడిగితే దానిని తెలుగులో మరింత వివరించగలను."


def _contains_telugu(text: str) -> bool:
    return any("\u0c00" <= char <= "\u0c7f" for char in text)


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


def _load_openwakeword_audio(path: str, mime_type: str = "audio/webm") -> tuple[Any | None, str]:
    audio, reason = _read_wav_for_openwakeword(path)
    if audio is not None:
        return audio, ""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None, f"{reason}; ffmpeg_missing_for_audio_decode"
    output_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
            output_path = handle.name
        process = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                path,
                "-ar",
                str(WAKE_SAMPLE_RATE),
                "-ac",
                "1",
                "-f",
                "wav",
                output_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if process.returncode != 0:
            return None, f"ffmpeg_audio_decode_failed: {process.stderr.decode(errors='ignore')[:160]}"
        return _read_wav_for_openwakeword(output_path)
    except Exception as exc:
        return None, f"audio_decode_failed: {exc}"
    finally:
        if output_path:
            Path(output_path).unlink(missing_ok=True)


def _read_wav_for_openwakeword(path: str) -> tuple[Any | None, str]:
    try:
        import numpy as np
    except Exception as exc:
        return None, f"numpy_unavailable_for_openwakeword: {exc}"
    try:
        with wave.open(path, "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            frame_rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except Exception as exc:
        return None, f"wav_read_failed: {exc}"
    if sample_width != 2:
        return None, f"unsupported_wav_sample_width: {sample_width}"
    if frame_rate != WAKE_SAMPLE_RATE:
        return None, f"unsupported_wav_sample_rate: {frame_rate}"
    audio = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return audio, ""


def _score_openwakeword_audio(model: object, audio: Any) -> dict[str, float]:
    try:
        import numpy as np
    except Exception:
        return {}
    scores: dict[str, float] = {}
    if len(audio) == 0:
        return scores
    for start in range(0, len(audio), WAKE_CHUNK_SAMPLES):
        chunk = audio[start : start + WAKE_CHUNK_SAMPLES]
        if len(chunk) < WAKE_CHUNK_SAMPLES:
            chunk = np.pad(chunk, (0, WAKE_CHUNK_SAMPLES - len(chunk))).astype(np.int16)
        prediction = model.predict(chunk)
        for name, score in _flatten_openwakeword_prediction(prediction).items():
            scores[name] = max(scores.get(name, 0.0), score)
    return scores


def _flatten_openwakeword_prediction(prediction: object) -> dict[str, float]:
    if not isinstance(prediction, dict):
        return {}
    scores: dict[str, float] = {}
    for name, value in prediction.items():
        if isinstance(value, dict):
            for child_name, child_score in _flatten_openwakeword_prediction(value).items():
                scores[f"{name}:{child_name}"] = child_score
            continue
        try:
            scores[str(name)] = float(value)
        except (TypeError, ValueError):
            continue
    return scores


def _wake_name_from_model_name(model_name: str) -> str:
    normalized = Path(model_name.split(":")[-1]).stem.lower().replace("_", " ").replace("-", " ")
    for wake_name in WAKE_NAMES:
        if wake_name in normalized:
            return wake_name
    return normalized.strip() or "custom_wake_word"


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
    preferred_terms = ("heera", "ravi", "hemant", "telugu", "india", "male", "david", "mark", "english")
    for voice in voices:
        label = f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')}".lower()
        if any(term in label for term in preferred_terms):
            try:
                engine.setProperty("voice", voice.id)
            except Exception:
                pass
            break
