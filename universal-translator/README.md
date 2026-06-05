# ULT - Universal Language Translator

ULT is a desktop-first real-time audio transformation app that sits between:

- microphone -> app
- system audio -> speaker

The current codebase targets:

- `Windows` as the primary runtime
- `Android` as a secondary scaffold/runtime path
- `Free stack` and `Paid-enhanced stack` in the same app

## Current Product Shape

ULT currently ships as one Electron desktop app with:

- microphone and speaker paths in one session
- free-only local/default behavior when no paid keys are configured
- paid-enhanced behavior when NVIDIA NIM, DeepL, OpenAI, or ElevenLabs keys are configured
- setup and launch through `setup.bat`, `run.exe`, and `tools/ult-doctor.js`
- desktop settings persisted under `.ult-runtime`

Main desktop entry points:

- `setup.bat`
- `run.exe`
- `electron/main.js`
- `electron/index.html`
- `electron/renderer.js`

Core runtime:

- `packages/ult-core/src/config.js`
- `packages/ult-core/src/stt-engine/index.js`
- `packages/ult-core/src/translation-engine/index.js`
- `packages/ult-core/src/tts-engine/tiered-speaker.js`
- `src/pipeline/realtime-translator.js`

## Engine Tiers

### Free Stack

Free stack is the default mode. It favors:

- local STT
- local/offline translation where available
- free-compatible speech output paths
- no paid provider usage

Typical components:

- Whisper / Vosk
- Marian / Argos
- Edge TTS / SAPI
- local routing and model assets

### Paid-Enhanced Stack

Paid-enhanced mode is optional. It activates only when the user selects paid mode and enters supported keys in the app.

Supported paid-enhanced providers:

- NVIDIA NIM for free hosted translation acceleration
- DeepL for translation
- OpenAI for speech generation
- ElevenLabs for higher-quality voice output

If keys are missing, ULT stays operational and falls back toward the free stack instead of breaking.

## What ULT Is Trying To Do

ULT aims to:

- intercept microphone audio before it reaches target apps
- intercept speaker/system audio before final playback
- translate speech into the selected target language
- preserve timing, voice feel, and emotion as closely as practical
- keep original audio blocked while ULT is active

## Current Engineering Priority

The next priority is to prove the real-time audio pipe before adding more AI behavior:

```text
capture audio -> replay unchanged -> measure latency
```

After that, add STT + TTS in the same language, then translation, then voice identity preservation.

See `docs/EXECUTION_ROADMAP.md` for the current execution order.

The deeper architecture blueprint lives in `docs/ULT_SYSTEM_BLUEPRINT.md`.

## What Is Implemented Today

- Electron desktop shell with start/stop, device selection, target language selection, and engine-tier settings
- free vs paid-enhanced engine routing with persisted API-key settings
- speaker and microphone pipelines running from one desktop session
- mic standby auto-activation
- speaker capture and translated-output pipeline
- runtime bootstrap inspection and doctor flow
- offline-first configuration support
- NVIDIA NIM translation integration through the OpenAI-compatible hosted endpoint
- DeepL translation integration for paid-enhanced mode
- Vosk fast-path wiring for lower-latency live speaker STT
- Experimental Animal Meaning Mode scaffold under `modules/animal_meaning`, backed by the downloaded BirdNET-Analyzer reference project.

## Animal Meaning Mode

This mode estimates possible animal/audio meaning from acoustic classification. It must not be presented as literal animal-to-English translation.

Reference project:

```text
C:\Users\balu\Projects\external-projects\BirdNET-Analyzer
```

Local module:

```text
modules/animal_meaning/
```

## What Still Requires Ongoing Work

The repo is advancing toward the ULT vision, but the hardest real-use requirements still need continued engineering work:

- consistently translated live speaker output at the target latency
- stronger mixed-audio speech replacement for songs and media
- stronger voice-identity preservation
- tighter routing guarantees under all Windows conditions
- packaging completion for polished Windows and Android release installs

## How To Run

### Windows launcher

```cmd
setup.bat
run.exe
```

`setup.bat` prepares dependencies and runtime folders. `run.exe` starts the Electron app.

### Development

```bash
npm install
npm run electron
```

## Verification

Core verification commands:

```bash
npm test
npm run typecheck
npm run build
npm run translation:check
npm run release:check
node tools/ult-doctor.js
```

## Runtime Settings

Desktop engine settings are stored in:

```text
.ult-runtime/desktop-settings.json
```

That file controls:

- `mode`
- `translationProvider`
- `nvidiaNimApiKey`
- `nvidiaNimModel`
- `deepLApiKey`
- `openAiApiKey`
- `elevenlabsApiKey`
- `elevenlabsVoiceId`

Translation provider values:

```text
auto     NVIDIA NIM -> DeepL -> Google worker -> local fallback
nvidia   NVIDIA NIM only for online translation
deepl    DeepL only for online translation
google   Google worker only for online translation
```

NVIDIA environment variables:

```text
NVIDIA_NIM_API_KEY=
NVIDIA_NIM_ENDPOINT=https://integrate.api.nvidia.com/v1/chat/completions
NVIDIA_NIM_TRANSLATION_MODEL=nvidia/riva-translate-4b-instruct-v1.1
ULT_TRANSLATION_PROVIDER=auto
```

## Project Notes

- Windows is the primary supported runtime.
- Android exists as a secondary path and scaffold, not yet feature-parity with Windows.
- Free stack remains the default and must continue working without paid keys.
- Paid-enhanced mode is additive, not mandatory.
