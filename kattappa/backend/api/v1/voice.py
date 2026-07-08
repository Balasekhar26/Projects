from fastapi import APIRouter, WebSocket, Header, HTTPException, Body
from typing import Any
from backend.api.v1.common import *

voice_router = APIRouter(tags=["Voice"])

@voice_router.get("/voice/status")
def voice_status() -> dict[str, object]:
    return voice_pipeline_status()



@voice_router.post("/voice/speak")
def voice_speak(request: VoiceSpeakRequest) -> dict[str, object]:
    spoken_text = normalize_spoken_text(request.text, purpose=request.purpose)
    if not spoken_text:
        return {"ok": False, "result": "empty_text", "pipeline": voice_pipeline_status()}
    import sys
    import backend.tools.voice_tools as _voice_tools
    _main_mod = sys.modules.get("backend.main")
    _speak_fn = getattr(_main_mod, "speak", None) or _voice_tools.speak
    return {
        "ok": True,
        "purpose": request.purpose,
        "spoken_text": spoken_text,
        "result": _speak_fn(spoken_text, purpose=request.purpose),
        "pipeline": voice_pipeline_status(),
    }



@voice_router.post("/voice/process")
def voice_process(request: VoiceAudioRequest) -> dict[str, object]:
    return process_voice_audio(
        request.audio_base64,
        mime_type=request.mime_type,
        model_size=request.model_size,
    )



@voice_router.post("/voice/parse-wake")
def voice_parse_wake(request: VoiceTranscriptRequest) -> dict[str, object]:
    return parse_wake_command(request.transcript)


# ── Streaming Voice Runtime WebSocket Endpoint ───────────────────────────────

from fastapi import WebSocketDisconnect
from backend.core.voice.runtime.websocket_protocol import VoiceStreamWebSocketHandler


@voice_router.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket) -> None:
    # Retrieve query params
    query_params = websocket.query_params
    session_id = query_params.get("session_id") or f"stream_{uuid.uuid4().hex[:8]}"
    voice_profile = query_params.get("voice_profile") or "kattappa"

    handler = VoiceStreamWebSocketHandler(websocket, session_id, voice_profile=voice_profile)
    await handler.handle_connection()





