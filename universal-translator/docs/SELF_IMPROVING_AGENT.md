# Self-Improving Agent

Universal Translator owns its own approval-gated improvement agent.

The agent observes project work, setup results, latency reports, audio-routing diagnostics, transcription/translation/TTS quality, and UI friction. It may propose improvements, but it must not enable paid engines, upload audio, change privacy settings, or install models without approval.

Improvement loop:

1. Observe local project signals: setup status, run status, tests, latency measurements, audio device errors, transcript errors, and repeated user actions.
2. Create a small proposal with motive, risk, files likely affected, verification plan, and rollback note.
3. Ask for approval before applying the proposal.
4. After approval, make the smallest useful change and run focused checks.
5. Write approved, sanitized lessons to the local project improvement registry.
6. On future runs, check the local registry for new proposals and ask approval before adopting them.

Local registry:

`docs\IMPROVEMENT_REGISTRY.md`

Boundaries:

- Fully free/open/local tools only.
- Offline-first STT, translation, TTS, and wake-word tooling.
- No paid API or cloud dependency in the core project.
- No covert recording, voice cloning, or audio upload.
- No raw audio, transcripts, private files, credentials, or speaker identity data are published.
