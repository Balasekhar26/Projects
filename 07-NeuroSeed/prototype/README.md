# NeuroSeed Pilot App

This is a static browser pilot app for Project 7.

Open `index.html` in a browser. No install step is required for browser-only mode.

For persistent local memory, start the project-owned backend first:

```bash
python3 ../backend/server.py
```

The pilot hydrates from and syncs to `http://127.0.0.1:8077`. Browser storage remains the fallback when the backend is unavailable.

## What It Demonstrates

- Paste learning content.
- Generate memory seeds.
- Approve seeds while awake.
- Play gentle sensory cues.
- Run a simulated sleep reinforcement session.
- Persist approved seeds, consent logs, study sessions, and recall checks in local memory.
- Check cued vs uncued recall across runs with keyword scoring.
- Export analysis JSON and recall CSV by explicit user action.
- Keep unapproved or unconscious-only injection locked.

## Boundary

This is not a real neurotechnology device. It is a software demonstrator for the safest buildable version of the motive: awake seeding plus low-strain sleep reinforcement.

The pilot data model keeps the consent boundary explicit: seeds include awake consent status, sessions include approved seed snapshots and cue events, and recall rows record whether each check was cued or uncued. Only awake-approved seeds are indexed for semantic recall; pending or removed seeds stay outside Chroma. Export remains an explicit UI action.
