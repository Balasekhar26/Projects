# Self-Improving Agent

NeuroSeed uses Kattappa AI OS as its approval-gated improvement agent.

The agent observes project work, setup results, prototype behavior, recall-check quality, consent-boundary clarity, accessibility issues, and UI friction. It may propose improvements, but it must not make clinical claims or add unconscious influence features.

Improvement loop:

1. Observe local project signals: setup status, run status, prototype errors, consent flow issues, recall results, and repeated user actions.
2. Create a small proposal with motive, risk, files likely affected, verification plan, and rollback note.
3. Ask for approval before applying the proposal.
4. After approval, make the smallest useful change and run focused checks.
5. Write approved, sanitized lessons to the Git shared improvement registry.
6. On future runs, check the Git registry for new proposals and ask approval before adopting them locally.

Shared registry:

`C:\Users\balu\Projects\kattappa\docs\SHARED_IMPROVEMENTS.md`

Boundaries:

- Fully free/open/local tools only.
- Consent-first learning reinforcement only.
- No paid API or cloud dependency in the core project.
- No memory-upload claims, unconscious persuasion, clinical claims, or unapproved sleep cueing.
- No raw study history, private files, medical data, or personal learning data are published.
