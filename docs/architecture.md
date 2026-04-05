# Universal Language Translator Architecture

## Workspace

- `packages/ult-core`: shared runtime contracts, device topology inspection, model-pack catalog, bootstrap logic, hybrid STT/translation/TTS adapters, voice-profile registry, live session orchestration, microphone routing control, audio blocking system, emotion detection, and first-run provisioning.
- `app/`: Next.js debug harness for inspecting runtime state and exercising the shared session contract from a browser microphone.
- `electron/`: Windows desktop shell that runs native capture through the shared runtime with microphone routing and audio blocking IPC handlers.
- `apps/android/`: Kotlin Android client with microphone translation core, sharing the same `StartSessionRequest` shape and playback-capture assumptions.
- `modules/mic-routing/`: Windows PowerShell-based virtual microphone driver detection and routing configuration.
- `modules/audio-blocking/`: WASAPI-based system audio endpoint muting for true audio replacement.
- `src/audio/: Emotion/expressiveness analysis for voice preservation.

## Runtime flow

1. **Initialization**: 
   - First-run wizard guides through setup (dependency verification, audio devices, language selection, voice profiles)
   - Bootstrap inspects hardware, installed runtimes, device topology, and temp-file state
   - Runtime directories and offline model packs are prepared

2. **Session Preparation**: 
   - Microphone routing established (physical mic → virtual device if configured)
   - Audio blocking enabled to mute original audio while translation plays
   - Unless explicitly online-only, offline Argos language pair is pre-downloaded

3. **Session Initialization**:
   - `StartSessionRequest` selects source language, target language, route profile, online policy, voice profile
   - Emotion detection is configured based on `preserveEmotion` flag

4. **Live Capture Loop**:
   - Rolling PCM commits with silence-aware boundaries and overlap to keep latency low
   - Source audio characteristics analyzed for emotion/expressiveness
   - Audio sent through hybrid STT → hybrid translation → tiered TTS with emotion preservation
   - Emotion-aware TTS instructions applied at synthesis time

5. **Session Events**:
   - `status` - session lifecycle events
   - `routing_state` - microphone/audio device status
   - `emotion_detected` - emotion classification with confidence
   - `partial_transcript` - interim transcription results
   - `partial_translation` - interim translation results
   - `final_translation` - confirmed translation chunks
   - `tts_started` / `tts_finished` - speech synthesis lifecycle
   - `latency_sample` - real-time performance measurements
   - `error` - exceptions and diagnostics

## Audio System Architecture

### Microphone Routing
- **Detection**: Enumerates Windows virtual audio devices (VB-Cable, Voicemeeter)
- **Configuration**: PowerShell-based setup with registry persistence
- **API**: IPC handlers (`microphone:setup`, `microphone:status`, `microphone:list-physical`, `microphone:list-virtual`, `microphone:check-driver`)
- **Fallback**: Gracefully continues using physical microphone if virtual device unavailable

### Audio Blocking
- **Method**: WASAPI endpoint volume control via P/Invoke
- **Scope**: System-wide muting of default playback device
- **State**: Tracks mute state explicitly, prevents state desync
- **Failsafe**: Automatic unmute on session end

### emotion Detection
- **Analysis**: Extracts pitch variation, energy, speech rate, pause frequency from source audio
- **Classification**: Maps features to emotion categories (anger, happiness, sadness, fear, surprise, neutral)
- **Confidence**: Returns numeric confidence scores per emotion
- **Instructions**: Generates natural language TTS instructions to preserve detected emotion
- **Fallback**: Text-based keyword detection when audio analysis unavailable
- **Logging**: Tracks emotion analysis results per session for diagnostics

### Speech Pipeline

**STT (Speech-to-Text)**:
- Default: Faster Whisper (local, offline, ~1.5s/chunk)
- Online fallback: OpenAI Whisper (when API available and configured)
- Integration: Automatic fallback between tiers with event emission

**Translation**:
- Default: Argos (local, offline, supports 100+ language pairs)
- Online fallback: LibreTranslate API (when network available and configured)
- Integration: Transparent tier switching, maintains language pair consistency

**TTS (Text-to-Speech)**:
- Tier 1: XTTS Voice Clone (offline, custom voices from consented profiles)
- Tier 2: OpenAI TTS (online, high-quality neural voices)
- Tier 3: Windows System TTS (offline, basic quality fallback)
- Tier 4: Silent (graceful degradation if all tiers fail)
- **Emotion Preservation**: Applicable TTS instructions applied at each tier
- **Logging**: Session-level tracking of fallback chain paths, success rates, emotion analysis

## Engine Strategy

**Online vs Offline**:
- Online mode (`onlinePolicy: "online-preferred"`): Uses cloud services with local fallbacks
- Offline mode (`onlinePolicy: "offline-only"`): Fails if cloud required, succeeds with local engines
- Hybrid mode (default): Tries online first, seamlessly falls back to local

**Voice Preservation**:
- Emotion/expressiveness analysis is performed on source audio
- Detected emotion is mapped to natural language TTS instructions
- Instructions are sent to TTS engines to match source intent
- Analysis confidence tracked for diagnostics
- Graceful fallback if source audio characteristics unavailable

**Quality vs Performance**:
- STT: ~1500ms target latency (helps ensure chunk boundaries don't clip sentences)
- Translation: <100ms (local library call)
- TTS: Depends on tier - XTTS ~2-3s, OpenAI ~1-2s, System <0.5s
- Overlap buffering during silence ensures natural transitions

## First-Run Setup Wizard

8-step interactive configuration:
1. Welcome screen with system overview
2. Dependency verification (Node, SoX, Python, models)
3. Audio device enumeration (physical and virtual)
4. Model directory prep and offline model status display
5. Target language selection (8 languages)
6. Voice profile configuration (optional, can defer)
7. System diagnostics validation
8. Completion summary with next steps

Wizard is event-driven, emits progress updates, can be re-run for reconfiguration.

## Testing

**E2E Test Suite** (`npm run test:e2e`):
- Device topology enumeration
- Microphone router functionality
- STT offline pipeline validation
- Translation engine operation
- TTS fallback chain initialization
- Audio latency measurement vs 1500ms target
- Device switching under load
- Offline-mode operation confirmation

**Unit Tests** (`npm test`):
- Component isolation validation
- Error handling paths
- Mock-based testing of cloud services

**Type Checking** (`npm run typecheck`):
- TypeScript validation across codebase
- API contract verification

## Packaging

**Windows**:
- **Format**: NSIS installer + portable EXE via electron-builder
- **Runtime Dependencies**: Copies `Scripts/`, `models/`, `sox-14.4.2/`, `tools/` into `resources/runtime/` 
- **State Directory**: Mutable state written to `LOCALAPPDATA/ULT Translator/.ult-runtime`
- **Artifacts**: `dist/windows/Universal Language Translator-X.X.X-setup.exe`, `-portable.exe`

**Android**:
- **Format**: APK or AAB via Gradle build system
- **Signing**: Via `apps/android/keystore.properties` or `ULT_ANDROID_*` environment variables
- **Runtime**: Microphone translation core in Kotlin with coroutine-based async processing
- **Limitations**: Speaker interception limited by Android system audio architecture (playback intercept not available to user apps)

**Setup & Build**:
Uses `setup-and-build.bat` batch orchestration:
- Prerequisite verification (winget, Node, Git, Android SDK where needed)
- Selective installation of missing components
- Dependency management via `npm install`
- Runtime provisioning via `npm run bootstrap:runtime`
- Automatic offline model preparation before session start
- Android SDK/PATH auto-configuration when available
