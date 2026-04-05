# Ultimate Translator

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

To capture system audio from a virtual audio cable, install SoX and make sure it is available on your `PATH`, then run:

```bash
npm run capture-audio
```

This will start recording from the configured capture device and save the audio to `system-audio.wav`.

## Real-Time Voice Translation And Cloning

This repo now includes a live translation app that can:

- capture microphone audio in the browser
- transcribe and translate short chunks continuously
- detect the emotion/expressiveness of the source audio
- generate translated speech with OpenAI TTS, preserving detected emotions
- route the translated audio to a Windows virtual audio device
- create and reuse consented custom cloned voices through the OpenAI Audio API

Run it with:

```bash
npm run dev
```

### Voice Emotion Preservation

The system includes automatic emotion detection that analyzes the source speaker's emotional characteristics and applies them to the translated output. This includes:

- **Emotion Classification**: Detects anger, happiness, sadness, fear, surprise, and neutral states
- **Feature Analysis**: Extracts pitch variation, energy levels, speech rate, and pause patterns
- **TTS Instruction Generation**: Generates natural language instructions for TTS engines to match the detected emotion
- **Multi-Tier Fallback**: Emotion information is preserved across TTS engine changes (XTTS → OpenAI → System TTS)
- **Session Logging**: Tracks emotion analysis confidence scores and fallback patterns for diagnostics

Enable emotion preservation with the `preserveEmotion: true` option when synthesizing speech.

## Electron Desktop Shell

A minimal Electron UI is included under `electron/` with:

- language selection
- a start/stop session button
- status log output

Files:

- `electron/main.js`
- `electron/preload.js`
- `electron/index.html`
- `electron/renderer.js`
- `electron/styles.css`

To run it after installing dependencies:

```bash
npm run electron
```

## Setup And Release Builds

Use the repo-native batch entrypoint on Windows:

```cmd
setup-and-build.bat setup
```

Supported modes:

- `setup-and-build.bat setup`
- `setup-and-build.bat verify`
- `setup-and-build.bat build-win`
- `setup-and-build.bat build-apk`
- `setup-and-build.bat build-aab`
- `setup-and-build.bat build-all`

### Testing

Run the E2E test suite to verify core system functionality:

```bash
npm run test:e2e
```

The E2E test suite includes:

- **Device Topology Test**: Verifies audio device enumeration (input/output devices)
- **Microphone Router Test**: Tests virtual microphone detection and routing configuration
- **Offline STT Test**: Validates offline speech-to-text with Whisper fallback
- **Translation Engine Test**: Tests translation pipeline with passthrough mode
- **TTS Fallback Chain Test**: Verifies TTS initialization and 4-tier fallback chain
- **Audio Latency Measurement**: Measures operation timing to ensure real-time performance
- **Device Switching Test**: Validates multiple input/output device support
- **Offline Mode Test**: Confirms system works without internet connectivity

Run unit tests with:

```bash
npm test
```

Run type checking:

```bash
npm run typecheck
```

### First-Run Setup Wizard

When launching for the first time, the system guides you through an 8-step setup process:

1. **Welcome** - Introduction and overview
2. **Dependency Verification** - Checks Node.js, SoX, Python availability
3. **Audio Device Discovery** - Detects physical and virtual microphones
4. **Model Directory Preparation** - Configures offline model storage
5. **Language Selection** - Choose from 8 supported languages (English, Telugu, Hindi, Spanish, French, German, Chinese, Japanese)
6. **Voice Profile Setup** - Optional custom voice configuration
7. **System Diagnostics** - Tests critical components
8. **Completion Summary** - Confirms successful setup

The wizard can be re-run manually if needed to reconfigure any settings.

### Audio Systems Architecture

**Microphone Routing**:
- Windows virtual audio device detection (VB-Cable, Voicemeeter)
- System microphone input enumeration
- Configurable device routing via `microphone:setup` IPC handler
- Route status monitoring and fallback support

**Audio Blocking**:
- WASAPI-based system audio endpoint muting
- Allows true system audio replacement (original blocked → translated routed)
- State tracking and graceful error recovery

**Speech Pipeline**:
- Real-time transcription with silence-aware chunking
- Hybrid STT: Faster Whisper (offline) + OpenAI Whisper (online)
- Multi-language translation: Argos (offline) + LibreTranslate (online)
- 4-tier TTS fallback: XTTS voice clone → OpenAI TTS → Windows System TTS → Silent graceful degradation

### What `setup-and-build.bat` Does

- verifies `winget`, Node.js, Git, VS Code, and Android Studio
- installs missing desktop prerequisites only when the selected mode allows installs
- installs project dependencies with `npm install`
- bootstraps runtime directories with `npm run bootstrap:runtime`
- auto-prepares transient runtime folders and attempts to provision the requested offline Argos language pair before a live session starts
- configures `ANDROID_HOME` and user `PATH` when an Android SDK already exists
- fails clearly when Android SDK tools or release signing are still missing

Android release signing:

1. Copy `apps/android/keystore.properties.example` to `apps/android/keystore.properties`
2. Fill in `storeFile`, `storePassword`, `keyAlias`, and `keyPassword`

You can also provide signing via environment variables instead:

- `ULT_ANDROID_KEYSTORE`
- `ULT_ANDROID_KEYSTORE_PASSWORD`
- `ULT_ANDROID_KEY_ALIAS`
- `ULT_ANDROID_KEY_PASSWORD`

Core implementation:

- `app/page.tsx`
- `app/api/models/route.ts`
- `app/api/realtime/sessions/route.ts`
- `app/api/audio/options/route.ts`
- `app/api/audio/voice-consents/route.ts`
- `app/api/audio/voices/route.ts`
- `app/api/realtime/sessions/[sessionId]/chunks/route.ts`
- `packages/ult-core/src/installer/provisioning.js`
- `packages/ult-core/src/installer/runtime-layout.js`
- `src/openai/audio.js`
- `src/tts/speaker.js`
- `src/server/realtime-session.js`

Environment variables:

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
$env:OPENAI_TTS_VOICE = "alloy"
$env:TTS_OUTPUT_DEVICE = "CABLE Input (VB-Audio Virtual Cable)"
$env:SOURCE_LANGUAGE = "te"
```

Notes:

- OpenAI custom voices are limited to eligible customers and require explicit consent plus a short audio sample.
- The app supports built-in OpenAI voices even if you have not created a custom voice yet.
- The app sends short chunk-level speaking instructions to TTS so translated playback better matches source energy and emotion.
- The actual voice clone quality depends heavily on the consent/sample recordings you provide.
- The bundled `sox-14.4.2/sox.exe` path is used by default to route generated WAV output to a Windows device.
- Desktop capture now uses silence-aware chunking with overlap instead of rigid fixed windows.
- Electron packaging now copies `Scripts/`, `models/`, `sox-14.4.2/`, and `tools/` into `resources/runtime/` so the packaged EXE can still find worker scripts and PowerShell helpers.
- Packaged runtime writes mutable data such as temporary audio, downloaded Argos packs, and local voice profile metadata to a user-writable `.ult-runtime` directory under `LOCALAPPDATA`.

Windows build artifacts:

- `dist/windows/Universal Language Translator-0.1.0-setup.exe`
- `dist/windows/Universal Language Translator-0.1.0-portable.exe`

Android packaging status:

- The Android project scaffold is included and build scripts are wired up.
- Building an APK or AAB still requires a local Android SDK plus release signing values (`apps/android/keystore.properties` or the `ULT_ANDROID_*` environment variables).

On Windows, SoX may not be available through Chocolatey. Instead, download it directly:

- Visit <https://sourceforge.net/projects/sox/>
- Download the Windows binary package
- Unzip and add the `sox` executable folder to your `PATH`

Then verify it is installed:

```powershell
sox --version
```

If you see `spawn sox ENOENT`, SoX is still not found by Node and needs to be added to your PATH.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
