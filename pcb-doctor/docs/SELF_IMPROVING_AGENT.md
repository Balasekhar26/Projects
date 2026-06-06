# Self-Improving Agent

PCB Doctor uses Kattappa AI OS as its approval-gated improvement agent.

The agent observes project work, setup results, test/build output, fault-classifier behavior, UI friction, and documentation gaps. It may propose improvements, but it must not edit files, install tools, change board schemas, or publish anything without approval.

Improvement loop:

1. Observe local project signals: setup status, run status, tests, build output, errors, repeated user actions, and missing diagnostics.
2. Create a small proposal with motive, risk, files likely affected, verification plan, and rollback note.
3. Ask for approval before applying the proposal.
4. After approval, make the smallest useful change and run focused checks.
5. Write approved, sanitized lessons to the Git shared improvement registry.
6. On future runs, check the Git registry for new proposals and ask approval before adopting them locally.

Shared registry:

`C:\Users\balu\Projects\kattappa\docs\SHARED_IMPROVEMENTS.md`

Boundaries:

- Fully free/open/local tools only.
- No paid API or cloud dependency in the core project.
- No destructive repair guidance without explicit approval.
- No raw user data, private files, credentials, or bench notes are published.
