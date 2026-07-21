"""WebSocket Protocol (Program 17.0).

Coordinates websocket transport, message frame routing, VAD turn-gating, STT, and TTS loops.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from backend.api.v1.common import _run_graph, memory
from backend.core.voice.runtime.voice_session import VoiceSession, VoiceState
from backend.core.voice.runtime.vad import VAD
from backend.core.voice.runtime.barge_in import BargeInEngine
from backend.core.voice.runtime.streaming_stt import StreamingSTT
from backend.core.voice.runtime.streaming_tts import StreamingTTS
from backend.core.voice.runtime.latency_metrics import LatencyMetrics
from backend.core.orchestrator.runtime import agent_events as ae

logger = logging.getLogger(__name__)


class VoiceStreamWebSocketHandler:
    """Manages full duplex lifecycle for voice stream websocket connections."""

    def __init__(self, websocket: WebSocket, session_id: str, voice_profile: str = "kattappa") -> None:
        self.websocket = websocket
        self.session = VoiceSession(session_id, voice_profile)
        self.vad = VAD()
        self.barge_in = BargeInEngine(self.session)
        self.telemetry = LatencyMetrics(self.session.session_id)

    async def handle_connection(self) -> None:
        """Core connection listener loop."""
        await self.websocket.accept()
        ae.emit_voice_telemetry(self.session.session_id, {"event": "connected"})

        await self.websocket.send_json({
            "type": "status",
            "status": "connected",
            "session_id": self.session.session_id
        })

        try:
            while True:
                message = await self.websocket.receive()

                if "bytes" in message:
                    await self._handle_audio_chunk(message["bytes"])

                elif "text" in message:
                    await self._handle_text_control(message["text"])

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("Error in VoiceStreamWebSocketHandler: %s", e)

    async def _handle_audio_chunk(self, chunk: bytes) -> None:
        """Processes binary PCM chunk."""
        # 1. Update activity timestamp
        self.session.update_activity()

        # 2. Check VAD energy & states
        vad_res = self.vad.process_chunk(chunk)
        has_voice = vad_res["has_voice"]
        event = vad_res["event"]

        # 3. Check for barge-in
        if self.barge_in.process_barge_in(has_voice):
            ae.emit_voice_telemetry(self.session.session_id, {"event": "barge_in"})
            await self.websocket.send_json({
                "type": "interrupted",
                "reason": "barge_in"
            })
            self.session.clear_input_buffer()
            return

        # 4. Turn state machine transitions
        if event == "speech_start":
            self.session.state = VoiceState.LISTENING
            self.telemetry.mark_turn_start()
            self.session.clear_input_buffer()
            self.session.append_input_audio(chunk)

        elif event == "speech":
            self.session.append_input_audio(chunk)

        elif event == "speech_end":
            self.session.state = VoiceState.PROCESSING
            await self._execute_cognitive_turn()

    async def _handle_text_control(self, text_msg: str) -> None:
        """Processes JSON control packet."""
        try:
            data = json.loads(text_msg)
            msg_type = data.get("type")
            if msg_type == "start":
                self.session.voice_profile = data.get("voice_profile", self.session.voice_profile)
                self.session.state = VoiceState.LISTENING
                await self.websocket.send_json({"type": "status", "status": "active"})
            elif msg_type == "stop":
                self.session.interrupted = True
                self.session.is_tts_playing = False
                await self.websocket.send_json({"type": "status", "status": "stopped"})
        except Exception:
            pass

    async def _execute_cognitive_turn(self) -> None:
        """Transcribes active speech, runs the HTN planner loop, and streams reply chunks."""
        audio_data = self.session.get_input_buffer()
        self.session.clear_input_buffer()

        if not audio_data:
            self.session.state = VoiceState.IDLE
            return

        # 1. Transcribe audio (STT)
        self.telemetry.mark_stt_start()
        stt_res = StreamingSTT.transcribe_segment(audio_data)
        self.telemetry.mark_stt_end()

        # Handle failed transcription
        if not stt_res["ok"]:
            reason = stt_res.get("reason", "")
            if "low_confidence" in reason:
                clarify_msg = "I did not understand clearly, my lord. Could you repeat that?"
                await self.websocket.send_json({
                    "type": "transcript",
                    "text": stt_res.get("transcript", ""),
                    "confidence": stt_res.get("confidence", 0.0),
                    "final": True,
                    "warning": "low_confidence"
                })
                await self._stream_response_tts(clarify_msg)
            else:
                self.session.state = VoiceState.IDLE
            return

        transcript = stt_res["transcript"]
        await self.websocket.send_json({
            "type": "transcript",
            "text": transcript,
            "confidence": stt_res["confidence"],
            "language": stt_res["language"],
            "final": True
        })

        # 2. Planning & Cognition Routing
        self.telemetry.mark_planning_start()
        import sys
        main_mod = sys.modules.get("backend.main")

        chat_session = memory.get_or_create_primary_chat_session()
        stored_user_message = memory.add_chat_message(chat_session["id"], "user", transcript)

        state = _run_graph(
            transcript,
            chat_session_id=chat_session["id"],
            current_chat_message_id=stored_user_message["id"],
            memory_query=transcript
        )
        result_text = str(state.get("result") or "")

        chat_state_metadata = getattr(main_mod, "_chat_state_metadata", None)
        metadata_json = chat_state_metadata(state) if chat_state_metadata else json.dumps({})
        memory.add_chat_message(
            chat_session["id"],
            "assistant",
            result_text,
            agent=str(state.get("selected_agent") or ""),
            risk=str(state.get("risk_level") or ""),
            metadata=metadata_json
        )

        self.telemetry.mark_planning_end()

        # 3. Stream reply back to client
        await self._stream_response_tts(result_text)

    async def _stream_response_tts(self, text: str) -> None:
        """Splits response text, streams binary synthesis packets, and transmits metrics."""
        self.session.state = VoiceState.SPEAKING
        self.session.is_tts_playing = True
        self.session.interrupted = False

        tts_engine = StreamingTTS(self.session)
        self.telemetry.mark_tts_start()
        first_chunk_sent = False

        # Generate audio iterator
        pcm_stream = tts_engine.generate_speech_stream(text)

        for chunk in pcm_stream:
            if self.session.interrupted:
                break

            await self.websocket.send_bytes(chunk)

            if not first_chunk_sent:
                first_chunk_sent = True
                self.telemetry.mark_tts_first_chunk()

            # Relinquish execution so concurrent reads on incoming user voice can barge-in
            await asyncio.sleep(0.001)

        # Transmit final telemetry payload
        if first_chunk_sent and not self.session.interrupted:
            metrics = self.telemetry.get_metrics_dict()
            await self.websocket.send_json({
                "type": "telemetry",
                "metrics": metrics
            })
            self.telemetry.publish_telemetry()

        self.session.is_tts_playing = False
        self.session.interrupted = False
        self.session.state = VoiceState.IDLE
