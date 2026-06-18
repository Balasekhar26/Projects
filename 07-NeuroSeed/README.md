# Project 7: NeuroSeed

NeuroSeed is a consent-first memory reinforcement concept. The realistic version pairs awake learning with gentle sleep-timed sensory cues to strengthen memories the user already studied and approved.

## Original Motive

NeuroSeed began as an idea for wirelessly injecting information into the human brain to reduce education time, so people could spend more time understanding, practicing, and applying skills.

That original motive is recorded here for project history. The buildable project must stay science-grounded: current science does not support direct wireless knowledge upload, unconscious information injection, or reliable memory copying. NeuroSeed should therefore be developed as learning acceleration and memory reinforcement, not brain upload.

## Stored Files

- `NeuroSeed_Dossier.md`: full concept dossier covering science, startup pitch, prototype roadmap, patent-style draft, research outline, sci-fi product design, ethics, and simple explainer.
- `prototype/`: local working prototype for seed generation, awake approval, sleep reinforcement simulation, and recall checks.
- `source-conversation.txt`: original pasted conversation/context that inspired the project.

## Run

```bat
setup.bat
run.exe
```

macOS/Linux can open the same local prototype directly:

```bash
python3 backend/server.py
python3 -m webbrowser prototype/index.html
```

## Core Positioning

NeuroSeed should be framed as memory reinforcement, not direct brain upload.

Best truthful sentence:

> NeuroSeed is a consent-first memory reinforcement system that helps users learn while awake and strengthen selected memories during sleep using gentle sensory cues.

Avoid claiming:

> NeuroSeed uploads information directly into the brain.

## Production Gate

- Keep `setup.bat` as the only setup entrypoint and `run.exe` as the only root run executable.
- Keep the prototype local-first with no network assets; `07-NeuroSeed/backend/server.py` owns the local SQLite/optional-Chroma memory backend at `http://127.0.0.1:8077`.
- Preserve the consent boundary: awake approval, user-selected content, local memory storage, and user-triggered export only.
- Do not claim direct brain upload, unconscious information injection, or memory copying.
