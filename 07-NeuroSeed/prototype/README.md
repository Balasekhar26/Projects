# NeuroSeed Pilot App

This is a static browser pilot app for Project 7.

Open `index.html` in a browser. No install step is required.

## What It Demonstrates

- Paste learning content.
- Generate memory seeds.
- Approve seeds while awake.
- Play gentle sensory cues.
- Run a simulated sleep reinforcement session.
- Persist study sessions in local browser storage.
- Check cued vs uncued recall across runs with keyword scoring.
- Export analysis JSON and recall CSV by explicit user action.
- Keep unapproved or unconscious-only injection locked.

## Boundary

This is not a real neurotechnology device. It is a software demonstrator for the safest buildable version of the motive: awake seeding plus low-strain sleep reinforcement.

The pilot data model keeps the consent boundary explicit: seeds include awake consent status, sessions include approved seed snapshots and cue events, and recall rows record whether each check was cued or uncued. Data remains local to the browser unless the user presses an export button.
