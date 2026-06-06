# Self-Improving Agent

AI Cyber Shield uses Kattappa AI OS as its approval-gated improvement agent.

The agent observes project work, setup results, scan behavior, alert quality, false positives, test/build output, and hardening report gaps. It may propose improvements, but it must not change firewall rules, process controls, credentials, or security settings without approval.

Improvement loop:

1. Observe local project signals: setup status, run status, tests, build output, scan output, incident reports, and repeated warnings.
2. Create a small proposal with motive, risk, files likely affected, verification plan, and rollback note.
3. Ask for approval before applying the proposal.
4. After approval, make the smallest useful change and run focused checks.
5. Write approved, sanitized lessons to the Git shared improvement registry.
6. On future runs, check the Git registry for new proposals and ask approval before adopting them locally.

Shared registry:

`C:\Users\balu\Projects\kattappa\docs\SHARED_IMPROVEMENTS.md`

Boundaries:

- Defensive use only.
- Fully free/open/local tools only.
- No paid API or cloud dependency in the core project.
- No automatic containment, firewall, credential, or process action without approval.
- No raw incident secrets, private files, credentials, or sensitive system details are published.
