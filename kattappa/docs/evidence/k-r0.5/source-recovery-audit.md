# K-R0.5 Source Recovery Audit: Voice and Orchestrator Runtime Modules

## Executive Summary
This document records the source provenance audit for the voice runtime and orchestrator runtime Python modules restored in `codex/k-r0.5-clean`. 

These modules were omitted from baseline commit `97d4bd9a5507479b5b5b903a9e09abf4bcc7b709` because `.gitignore` contained a recursive `runtime/` ignore rule (`**/runtime/`). This rule was intended to ignore ephemeral test artifacts, but unintentionally masked `backend/core/voice/runtime/` and `backend/core/orchestrator/runtime/`.

## Restored Module Inventory & SHA-256 Hashes

| Path | SHA-256 Hash | Original Purpose | Baseline Exclusion Cause | Review Status |
| :--- | :--- | :--- | :--- | :--- |
| `backend/core/voice/runtime/__init__.py` | `E3B0C44298FC1C149AFBF4C8996F...` | Package initialization | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/voice/runtime/barge_in.py` | `DB926FF...` | Voice stream barge-in detection | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/voice/runtime/emotion_tts.py` | `100A4E8...` | Emotion TTS voice routing | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/voice/runtime/jitter_buffer.py` | `5AF9730...` | Audio packet jitter buffering | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/voice/runtime/latency_metrics.py` | `F6F3D71...` | Voice latency telemetry | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/voice/runtime/streaming_stt.py` | `52C1412...` | Streaming STT processing | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/voice/runtime/streaming_tts.py` | `16C1799...` | Streaming TTS processing | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/voice/runtime/telugu_helper.py` | `F2409C1...` | Telugu voice synthesis helper | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/voice/runtime/vad.py` | `54F2E99...` | Voice activity detection | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/voice/runtime/voice_session.py` | `2272F2B...` | Voice session state manager | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/voice/runtime/websocket_protocol.py` | `A2DED3F...` | WebSocket voice streaming protocol | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/orchestrator/runtime/__init__.py` | `E3B0C44298FC1C149AFBF4C8996F...` | Package initialization | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/orchestrator/runtime/agent_budget.py` | `7BACF98...` | Orchestrator agent token budget | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/orchestrator/runtime/agent_events.py` | `CFE2EDA...` | Agent runtime event models | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/orchestrator/runtime/deadlock_detector.py` | `6E16259...` | Runtime graph deadlock detection | Masked by `.gitignore` | Approved (Outcome A) |
| `backend/core/orchestrator/runtime/task_fingerprint.py` | `6723D3E...` | Task fingerprinting & hashing | Masked by `.gitignore` | Approved (Outcome A) |

## Architectural Outcome Classification

**Chosen Outcome**: **Outcome A (Proven Missing Baseline Source)**

### Justification:
1. **Import Lineage Proof**: `backend/api/v1/voice.py` directly imports `backend.core.voice.runtime.websocket_protocol.VoiceStreamWebSocketHandler`. `websocket_protocol.py` directly imports `backend.core.orchestrator.runtime.agent_events`. Without these files, importing `backend/main.py` fails.
2. **Zero Feature Expansion**: No new API endpoints or cognitive algorithms were added in these files. They reflect existing codebase implementation required by existing unit and integration tests.
3. **Ignore Rule Fix**: `.gitignore` has been updated with explicit un-ignore rules (`!backend/core/voice/runtime/` and `!backend/core/orchestrator/runtime/`) so these files remain tracked in Git.
