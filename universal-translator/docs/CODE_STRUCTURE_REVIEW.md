# Code Structure Review

Date: 2026-05-09

## Summary

The repo is not a simple translator app. It is already a multi-runtime product with:

- Electron desktop shell in `electron/`
- Next.js app/API routes in `app/`
- Core runtime package in `packages/ult-core/`
- Windows audio/routing modules in `modules/`
- Python/audio runtime assets in `Scripts/`, `models/`, and `sox-14.4.2/`
- Android scaffold in `apps/android/`
- runtime diagnostics in `tools/`

The strongest architectural choice is that the realtime pipeline is separated from capture, STT, translation, TTS, audio blocking, and device topology. That is the right direction for a hard app like ULT.

## What Was Improved

The translation layer had a partially built NVIDIA NIM client, but the hybrid translation engine did not route through it. The Electron UI also had no NVIDIA settings fields.

This pass added:

- NVIDIA NIM as a first-class translation provider.
- Provider order: NVIDIA NIM -> DeepL -> Google worker -> Argos -> MarianMT.
- `ULT_TRANSLATION_PROVIDER` to force `auto`, `nvidia`, `deepl`, or `google`.
- Offline-first default policy in core config.
- Lazy worker startup so tests and app startup do not spawn translation workers unnecessarily.
- Electron settings for NVIDIA key and model override.
- Non-breaking paid mode: missing paid keys now logs warnings and falls back instead of blocking startup.
- Release and offline translation check tools.

## High-Priority Structure Notes

1. `packages/ult-core/src/translation-engine/` is the right home for provider selection. Keep provider logic out of Electron UI and API routes.

2. `electron/main.js` is still large. Its next refactor should extract desktop settings and provider readiness into a small module, for example:

```text
electron/runtime-settings.js
electron/provider-readiness.js
```

3. Runtime assets are mixed into the active repo (`Scripts/`, `models/`, `sox-14.4.2/`). This is practical for a laptop build, but release packaging should treat them as runtime assets, not source code.

4. The app has both Electron and Next API entry points. Keep both wired through `packages/ult-core` so they do not drift into separate products.

5. The most valuable next tests are provider-order tests and Electron settings persistence tests.

## New Commands

```bash
npm run translation:check
npm run release:check
npm test -- packages/ult-core/tests/translation-engine.test.js
```

## Release Recommendation

Before publishing a Windows release:

1. Run `npm test`.
2. Run `npm run typecheck`.
3. Run `npm run translation:check`.
4. Run `npm run release:check`.
5. Run `node tools/ult-doctor.js` on the release machine.
6. Build with `npm run package:windows`.
