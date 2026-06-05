# ULT System Blueprint

ULT means: change language while preserving the human.

## Four Laws

1. Content changes: language can change.
2. Identity stays: voice identity should remain recognizable.
3. Emotion stays: pitch, intensity, rhythm, and tone should survive the transformation.
4. Continuity stays: timing should feel continuous, not stitched together.

## Seven Layers

1. Audio interception: capture speaker and microphone paths before final output.
2. Temporal buffer engine: convert continuous audio into overlapping low-latency chunks.
3. STT: produce text, timing, confidence, and partial results.
4. Semantic translation: translate meaning with context, not word-by-word replacements.
5. Voice identity: extract and preserve speaker identity and expressive metadata.
6. Audio reconstruction: align generated speech to the original timing budget.
7. Output injection: send the transformed audio to speaker or virtual microphone.

## Build Order

```text
capture -> pass-through -> latency measurement -> STT -> TTS -> translation -> voice identity -> timing polish
```

The first product milestone is not perfect translation. It is stable pass-through with honest latency measurement.

## Current Code Anchors

| Layer | Code anchor |
| --- | --- |
| Audio interception | `src/audio/capture.js`, `modules/audio-capture/`, `modules/mic-routing/` |
| Temporal buffering | `packages/ult-core/src/audio-capture/ring-buffer.js`, `src/pipeline/realtime-translator.js` |
| STT | `packages/ult-core/src/stt-engine/` |
| Translation | `packages/ult-core/src/translation-engine/` |
| Voice identity | `packages/ult-core/src/voice-identity/`, `src/audio/expressiveness.js` |
| Audio reconstruction | `packages/ult-core/src/tts-engine/playback-controller.js`, `src/pipeline/utterance-manager.js` |
| Output injection | `packages/ult-core/src/tts-engine/`, `packages/ult-core/src/mic-routing/` |

## Latency Budget

Target practical v1:

```text
buffer: 300-500 ms
STT: 200-500 ms
translation: 50-200 ms
TTS: 300-800 ms
total: 1-2 seconds
```

Future target:

```text
partial streaming path below 500 ms perceived response
```
