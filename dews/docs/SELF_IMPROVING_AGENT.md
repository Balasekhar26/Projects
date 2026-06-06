# Self-Improving Agent

DEWS uses Kattappa AI OS as its approval-gated improvement agent.

The agent observes project work, setup results, simulation output, false-positive patterns, safety-boundary warnings, UI friction, and report quality. It may propose improvements, but it must keep this project strictly in safe detection, alerting, reporting, and simulation.

Improvement loop:

1. Observe local project signals: setup status, run status, tests, build output, simulation output, alert behavior, and repeated user actions.
2. Create a small proposal with motive, risk, files likely affected, verification plan, and rollback note.
3. Ask for approval before applying the proposal.
4. After approval, make the smallest useful change and run focused checks.
5. Write approved, sanitized lessons to the Git shared improvement registry.
6. On future runs, check the Git registry for new proposals and ask approval before adopting them locally.

Shared registry:

`C:\Users\balu\Projects\universal-ai\docs\SHARED_IMPROVEMENTS.md`

Boundaries:

- Detection, simulation, alerts, and reports only.
- Fully free/open/local tools only.
- No paid API or cloud dependency in the core project.
- No destructive emitters, targeting logic, weapon disablement, or autonomous engagement.
- No raw sensitive security footage, private files, or location-sensitive details are published.
