# Production Readiness Standard

This workspace has seven canonical projects:

1. `universal-ai`
2. `pcb-doctor`
3. `ai-cyber-shield`
4. `universal-translator`
5. `musical-keyboard`
6. `dews`
7. `07-NeuroSeed`

Use `bin\CHECK_PRODUCTION_READINESS.bat` before committing or packaging. Use
`bin\CHECK_PRODUCTION_READINESS.bat -Full` when you also want frontend build checks.

## Shared Gate

Each project must have:

- A canonical top-level folder listed in `bin\PROJECTS_INDEX.md`.
- A README or project notes that state what the project does.
- Exactly one root setup entrypoint: `setup.bat`.
- Exactly one root run executable: `run.exe`.
- A repeatable test, compile, or build check.
- Runtime/generated files ignored by git.
- No nested git repositories inside project folders.

## Project-Specific Gate

### Universal AI

- Core backend modules must compile.
- Environment examples must exist.
- File, terminal, browser, and system-changing actions must route through an
  approval boundary before execution.
- Memory storage must be bounded by decay, summary, or pruning policy.

### PCB Doctor

- Board JSON and measurement files must be validated before diagnosis.
- Full unit tests must pass without requiring private external checkouts.
- Findings must include confidence, severity, and technician-facing next steps.

### AI Cyber Shield

- The ASA pipeline must run as one workflow and continue after non-fatal layer
  failures.
- Runtime logs, evidence, blocklists, and honeypot contents must remain local and
  untracked except placeholder `.gitkeep` files.
- Auto-containment must stay disabled by default unless an operator explicitly
  enables it in policy.

### Universal Translator

- Tests must pass.
- STT worker startup must fail fast when required local models or scripts are
  missing.
- Runtime audio, model, and virtual environment artifacts must remain untracked.
- Paid or online engines must never become the default path.

### Musical Keyboard

- TypeScript must pass.
- AudioContext lifecycle, key-repeat prevention, and polyphony limits must be
  enforced.
- Build artifacts must remain untracked.

### DEWS

- The implementation must stay in the safe simulation and early-warning domain.
- It must not include targeting, engagement, weapon-disabling, or directed-energy
  control logic.
- Unit tests must verify protective actions are alert, isolate, evacuate, log, or
  monitor actions only.

### NeuroSeed

- The prototype must run locally without network assets.
- It must preserve the consent boundary: awake approval, user-selected content,
  local storage, and user-triggered export only.
- It must avoid claims of direct brain upload, unconscious information injection,
  or memory copying.
