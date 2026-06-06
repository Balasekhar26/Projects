# Self-Improving Agent

Musical Keyboard uses Kattappa AI OS as its approval-gated improvement agent.

The agent observes project work, setup results, build output, audio glitches, input latency, browser compatibility, PWA install behavior, and UI friction. It may propose improvements, but it must not add copyrighted samples, paid services, or broad rewrites without approval.

Improvement loop:

1. Observe local project signals: setup status, run status, tests, build output, audio/input bugs, and repeated user actions.
2. Create a small proposal with motive, risk, files likely affected, verification plan, and rollback note.
3. Ask for approval before applying the proposal.
4. After approval, make the smallest useful change and run focused checks.
5. Write approved, sanitized lessons to the Git shared improvement registry.
6. On future runs, check the Git registry for new proposals and ask approval before adopting them locally.

Shared registry:

`C:\Users\balu\Projects\kattappa\docs\SHARED_IMPROVEMENTS.md`

Boundaries:

- Fully free/open/local tools only.
- Copyright-safe or generated/open samples only.
- No paid API or cloud dependency in the core project.
- No raw private recordings are published.
