# ULT Execution Roadmap

ULT is the first system to finish because it owns the hardest shared problem: real-time audio routing.

## Product Definition

ULT is a real-time audio transformation engine:

```text
input audio -> capture -> optional STT -> optional translation -> optional TTS -> routed output
```

The first serious milestone is not translation. It is pass-through:

```text
input audio -> capture -> routed output
```

## Milestone 1: Pass-Through Mode

Build a mode that captures audio and plays it back unchanged.

Required behavior:

- selectable source device
- selectable output route
- start/stop from Electron
- latency measurement for capture -> output
- fail-closed when routing is invalid

Success means ULT can prove the audio pipe works before AI enters the loop.

## Milestone 2: STT + TTS Without Translation

Build a speech loop that transcribes and speaks back in the same language.

Required behavior:

- chunked STT
- partial transcript support
- TTS playback queue
- silence skip
- latency per stage

Success means ULT can survive real-time speech timing.

## Milestone 3: Translation

Add translation after the same-language speech loop is stable.

Required behavior:

- local/free provider first
- paid provider fallback only when configured
- phrase buffering for language reorder
- visible latency budget

## Milestone 4: Voice Identity

Only after the loop is stable:

- profile speaker tone
- preserve pitch/pace/emotion metadata
- apply voice clone or style transfer when consent/config allows it
- keep generic TTS fallback available

## Files To Touch First

- `src/pipeline/realtime-translator.js`
- `src/audio/capture.js`
- `packages/ult-core/src/audio-routing/route-profiles.js`
- `packages/ult-core/src/tts-engine/playback-controller.js`
- `tools/ult-doctor.js`

## Files To Avoid Treating As Core Source

- generated dependency folders
- virtual environments
- model caches
- old merged project copies
- local `.env` files

Those belong outside the repo surface unless packaging explicitly requires them.
