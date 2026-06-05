# Five Project Deepening Notes

This pass keeps the `universal-translator/` migration intact while adding focused
project work from the planning notes.

## Universal AI

- Memory rows now carry `decay_score`, `last_accessed`, and
  `flagged_for_summary`.
- `MemorySystem.decay_memories()` applies bounded score decay, flags low-value
  memories for summarisation, and prunes expired rows.

## PCB Doctor

- Board JSON loading now validates required node ids, duplicate ids, expected
  ranges, and upstream references.
- Measurement loading rejects impossible physical readings before they enter the
  diagnostic classifier.

## AI Cyber Shield

- `asa.pipeline.run_pipeline()` chains scan, detect, response, hardening,
  optional baseline learning, and optional report writing through one shared
  report object.
- The CLI has a `pipeline` command with `--save-baseline` and `--write-report`.
- A layer failure is logged and recorded without stopping later safe layers.

## Universal Translator

- The Vosk STT engine now fails fast when the Python worker or model path is
  missing.
- Vosk requests now have a timeout, and `stop()` rejects outstanding work.

## Musical Keyboard

- Active voices are capped at 16 with oldest-voice stealing.
- Held keys no longer retrigger while already active.
- Window blur and tab hide release all notes.
- On-screen keys use pointer events for mouse, touch, and hybrid devices.
