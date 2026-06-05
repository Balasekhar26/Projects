# Universal Language Translator Architecture

## Workspace

- `packages/ult-engine`: C++ and Python native audio daemon. Handles absolute lowest-level WASAPI Exclusive / PortAudio bindings for direct memory manipulation of audio buffers.
- `packages/ult-core`: Electron UI and state synchronization with the native daemon.
- `apps/android/`: Native Android audio hook system using C++ Oboe / AudioRecord API for deep system capture.
- `modules/mic-routing/`: Windows PowerShell-based virtual microphone driver detection and routing configuration.
- `modules/audio-blocking/`: WASAPI-based system audio endpoint muting for true audio replacement.
- `modules/stem-separation/`: Demucs integration for real-time background noise/music extraction.
- `src/audio/`: Emotion/expressiveness analysis for voice preservation mapping into RVC/XTTS.

## Runtime flow

1. **Initialization**: 
   - First-run wizard guides through setup (dependency verification, audio devices, language selection, voice profiles)
   - Bootstrap inspects hardware, installed runtimes, device topology, and temp-file state
   - Runtime directories and offline model packs are prepared

2. **Session Preparation**: 
   - **Always-ON Engine Engaged**: Simultaneous WASAPI loops initialized for both microphone AND speaker paths. No manual mode switching is allowed.
   - Original hardware endpoints muted at the OS level; virtual endpoints take over entirely.
   - Offline MarianMT/NLLB language models loaded into VRAM.

3. **Live Capture Loop (Continuous Streaming)**:
   - Native daemon reads PCM streams at 16kHz continuously.
   - Audio passes through Demucs. Voice stems go to Whisper, instrumental stems bypass for later recomposition.
   - **7-Step Pipeline:** Speech Extraction → STT (Whisper) → Translation (NLLB) → Voice Reconstruction (Coqui TTS/RVC) → Prosody Transfer → Audio Recomposition → Output Routing.
   - Translated voice fused with original instrumental stem.
   - Recomposed audio injected to Virtual Mic and Virtual Speaker within **< 300ms latency requirement**.

4. **Temporal Contract (GETS)**:
   - All causally relevant runtime events must conform to the Global Event Time System contract in [docs/global-event-time-spec.md](/c:/Users/balu/Projects/ult-translator/docs/global-event-time-spec.md).
   - Cross-subsystem decisions must use `normalizedTime` rather than raw local clocks.
   - Replay and observer analysis must preserve quota/backpressure timing as a first-class input.

5. **Session Events**:
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
- Default: Whisper (ONNX / TensorRT optimized for C++)

**Translation**:
- Default: MarianMT / NLLB (CTranslate2 optimized, offline)

**TTS (Text-to-Speech)**:
- Tier 1: Coqui TTS / RVC (Voice Cloning, offline)
- **Emotion Preservation**: Applicable TTS instructions applied at each tier
- **Logging**: Session-level tracking of fallback chain paths, success rates, emotion analysis

## Engine Strategy

**Voice Preservation**:
- Emotion/expressiveness analysis is performed on source audio
- Detected emotion is mapped to natural language TTS instructions
- Instructions are sent to TTS engines to match source intent
- Analysis confidence tracked for diagnostics
- Graceful fallback if source audio characteristics unavailable

**Quality vs Performance**:
- Entire pipeline tuned for **sub-300ms latency** using C++ PortAudio and GPU acceleration.

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
