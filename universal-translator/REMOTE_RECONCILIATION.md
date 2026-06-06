# Remote Reconciliation Notes

Local `main` diverged from `origin/main` after the local cleanup commits:

- Local-only: `07f7d967e` and `f556d60a4`, which cleaned the initial ULT import and removed large generated files.
- Remote-only: ULT feature/docs/sync commits, Balu Cyber Shield commits, workspace organization, and Universal AI tooling commits.

## Kept

- ULT feature work, setup docs, sync tooling, app/runtime code, tests, and package metadata under `universal-translator/`.
- Cyber Shield source, dashboard, policy/config, tests, honeypot seed files, and launch scripts under `ai-cyber-shield/`.
- Kattappa source, desktop app, backend, docs, tests, and launcher scripts now live under its own standalone `kattappa/` project folder.
- Existing top-level project structure for `pcb-doctor/` and `musical-keyboard/`.
- Workspace-level README, project index, and check script using canonical top-level project paths.

## Dropped Or Ignored

- The retired `ult-translator/` path.
- Python virtual environment content: `Lib/`, `Include/`, `Scripts/`, `pyvenv.cfg`, and `__pycache__/`.
- Audio captures and runtime stores: `*.wav`, `*.db`, `.tmp/`, `.ult-runtime/`, setup flags, and local logs.
- Vendor/reference payloads: `share/`, `sox-*`, `models/`, package build outputs, Electron packaged output, and root `bin/`.
- Nested Git metadata. The previous embedded `universal-translator/.git` was moved locally to `.local-git-backups/universal-translator.git` and is ignored.

The canonical translator path is now `universal-translator/`; do not add new source under `ult-translator/`.
