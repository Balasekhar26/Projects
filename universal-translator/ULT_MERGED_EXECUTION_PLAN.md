# ULT Merged Execution Plan

This is the selected execution plan for the repo.

It merges:

- the user's full ULT vision
- the free-stack execution doctrine
- the paid-enhanced execution doctrine
- the practical architecture already present in this codebase

## Selected Plan

ULT is built as one product with two engine tiers:

- `Free mode`
- `Paid-enhanced mode`

The same external product behavior applies to both:

- mic path and speaker path in one app
- original audio blocked while active
- translated output favored over original output
- minimal user controls
- automatic runtime logic

## Why This Is The Picked Plan

This plan is the strongest option because it preserves the product vision while matching the real codebase:

- free mode stays local/free-first and keeps core functionality available without paid keys
- paid-enhanced mode layers higher-quality providers on top of the same app instead of creating a separate product
- the architecture remains modular enough for Windows-first delivery and Android expansion

## Tier Definitions

### Free Mode

Primary target:

- satisfy the ULT requirements as closely as practical with free or local components

Preferred stack:

- STT: Whisper, Vosk
- Translation: Marian, Argos
- TTS: Edge TTS, SAPI, XTTS when local consented voice profiles exist
- Audio routing: VB-Cable and Windows route helpers
- Separation and prosody: local workers where available

Operational doctrine:

- local and free-compatible providers only
- offline-first behavior
- preserve core functionality even when quality features must degrade

### Paid-Enhanced Mode

Primary target:

- push the same ULT app closer to product-grade quality using optional premium providers

Preferred stack:

- Translation: DeepL
- Speech generation: OpenAI
- Premium voice output: ElevenLabs
- Local voice profiles and local prosody/background handling remain available

Operational doctrine:

- use premium providers only when keys are available
- keep the same routing/session architecture
- fall back gracefully if one premium provider is unavailable

## Build Order

### Stage 1: Core Runtime Integrity

Deliverables:

- lazy config resolution
- no import-time worker startup
- stable tests, typecheck, and build
- fail-closed session and routing contracts

Status:

- implemented

### Stage 2: One App, Two Tiers

Deliverables:

- desktop settings persistence
- engine tier selector
- paid provider key inputs
- automatic free fallback when keys are absent

Status:

- implemented

### Stage 3: Speaker Path Reliability

Deliverables:

- stable speaker capture
- translated speaker output path
- faster speaker STT
- better queue/latency controls

Status:

- in active progress

### Stage 4: Voice Identity

Deliverables:

- consented local voice profile support
- stronger XTTS path usage
- desktop/runtime use of the best available local voice profile

Status:

- partial, improved in current repo

### Stage 5: Emotion And Prosody

Deliverables:

- extract source prosody
- apply prosody to translated speech
- preserve timing and speaking feel more closely

Status:

- partial foundation present

### Stage 6: Mixed Audio Recomposition

Deliverables:

- preserve background audio
- replace speech layer only
- improve songs/media behavior

Status:

- partial foundation present

### Stage 7: Packaging And Release

Deliverables:

- Windows installer
- Android build path
- first-run dependency/bootstrap checks

Status:

- bootstrap/doctor present, release hardening still in progress

## Current Implementation Mapping

Desktop app:

- `electron/main.js`
- `electron/preload.js`
- `electron/index.html`
- `electron/renderer.js`

Core engines:

- `packages/ult-core/src/config.js`
- `packages/ult-core/src/stt-engine/index.js`
- `packages/ult-core/src/translation-engine/index.js`
- `packages/ult-core/src/tts-engine/tiered-speaker.js`
- `src/pipeline/realtime-translator.js`

Startup and environment:

- `ULT.bat`
- `tools/ult-doctor.js`

## Success Criteria

This repo should keep moving toward these checkpoints:

- free mode works without paid keys
- paid-enhanced mode upgrades quality when keys are present
- both mic and speaker paths are managed by one runtime
- translated output remains the intended output path
- routing/bootstrap checks happen automatically
- verification remains green after each change
