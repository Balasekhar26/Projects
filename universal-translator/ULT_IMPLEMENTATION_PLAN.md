# ULT Implementation Plan

This file maps the current repo to the ULT execution direction.

## Execution Model

ULT is being built as one application with two engine tiers:

- `Free stack`
- `Paid-enhanced stack`

The external workflow stays the same in both tiers:

- choose mic device
- choose speaker device
- choose mic target language
- choose speaker target language
- start or stop the session

## Tier Strategy

### Free Stack

Goal:

- stay as close as possible to the ULT vision with local and free-compatible components

Preferred components:

- STT: Whisper and Vosk
- Translation: Marian and Argos
- TTS: Edge TTS, SAPI, local XTTS where available
- Routing: VB-Cable / Windows routing helpers

### Paid-Enhanced Stack

Goal:

- improve quality, voice realism, and translation quality when provider keys are available

Preferred components:

- Translation: DeepL
- Speech generation: OpenAI
- Voice output enhancement: ElevenLabs

If paid keys are absent, ULT must still run by falling back toward the free stack.

## Current Code Ownership

Desktop shell:

- `electron/main.js`
- `electron/preload.js`
- `electron/index.html`
- `electron/renderer.js`

Core runtime:

- `packages/ult-core/src/config.js`
- `packages/ult-core/src/stt-engine/index.js`
- `packages/ult-core/src/translation-engine/index.js`
- `packages/ult-core/src/tts-engine/tiered-speaker.js`
- `src/pipeline/realtime-translator.js`
- `src/audio/capture.js`
- `packages/ult-core/src/audio-capture/ring-buffer.js`

Provisioning and startup:

- `ULT.bat`
- `tools/ult-doctor.js`

## Build Order

### Phase 1: Stable Core Session

Target:

- one desktop session owning both mic and speaker paths
- lazy config and safe runtime startup
- no import-time worker startup
- passing tests, typecheck, and build

Status:

- implemented

### Phase 2: Free/Paid Tier Routing

Target:

- desktop UI exposes free vs paid-enhanced mode
- provider keys persist locally
- runtime chooses free or paid-enhanced components automatically

Status:

- implemented

### Phase 3: Speaker Path Reliability

Target:

- stable speaker capture
- translated speaker audio handoff
- lower-latency live speaker STT
- no silent failure when speaker path is active

Status:

- in active progress

Main files:

- `electron/main.js`
- `src/pipeline/realtime-translator.js`
- `packages/ult-core/src/stt-engine/index.js`
- `Scripts/vosk_stream_worker.py`
- `Scripts/whisper_stream_worker.py`

### Phase 4: Voice Identity And Prosody

Target:

- stronger voice identity preservation
- stronger emotional/prosody carryover
- better mapping between source speaker feel and translated output

Status:

- partial foundation present

Main files:

- `packages/ult-core/src/voice-clone/xtts.js`
- `packages/ult-core/src/voice-clone/registry.js`
- `packages/ult-core/src/prosody/engine.js`
- `packages/ult-core/src/tts-engine/tiered-speaker.js`

### Phase 5: Mixed Audio Recomposition

Target:

- preserve non-speech background audio
- replace speech layer only
- improve song and media handling

Status:

- partial foundation present, not complete

Suggested next modules:

- `Scripts/audio_separator_worker.py`
- `packages/ult-core/src/audio-separation/separator.js`

### Phase 6: Packaging

Target:

- one Windows installer
- one Android build path
- dependency/bootstrap checks on first run

Status:

- desktop bootstrap and doctor flow present
- Android path scaffolded
- final packaging still needs hardening

## Near-Term Priorities

1. Make translated live speaker output more reliable in real use.
2. Improve paid-enhanced provider selection and runtime observability.
3. Improve mixed-audio speech replacement.
4. Strengthen voice-preserving output path.
5. Harden packaging and release flow.

## Acceptance Direction

ULT should be judged by these practical checkpoints:

- mic and speaker paths run from one app session
- free stack works without paid keys
- paid-enhanced stack improves quality when keys are present
- original audio is blocked while ULT is active
- translated output is the dominant output path
- build, tests, and doctor remain green after changes
