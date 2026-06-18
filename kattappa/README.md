# Kattappa AI OS Assistant

Fully free, local-first AI OS assistant. It responds to Kattappa, Mama, and Kittu when voice listening is enabled.

## Supported Windows Launch Path

First run:

```bat
setup.bat
```

Normal launch after setup:

```bat
run.exe
```

The root setup file and run executable own the Windows flow:

1. Creates or reuses `ai_system_env`.
2. Writes `backend\.env`.
3. Installs backend and desktop UI dependencies.
4. Starts Ollama only when the `ollama` command is installed.
5. Starts or reuses the FastAPI backend on `http://127.0.0.1:8000`.
6. Opens the native desktop app when it has been built.
7. Falls back to the same React desktop UI at `http://127.0.0.1:5173` on a fresh install.

Supported commands:

```bat
run.exe            # run app
run.exe services   # backend/services only
run.exe backend    # backend only
run.exe ui         # browser desktop UI
run.exe dev        # backend + Tauri dev app
run.exe build      # build native Windows desktop app
run.exe status     # backend health
run.exe stop       # stop services started by Kattappa AI OS
```

## macOS/Linux Native Desktop Launch

On macOS and Linux, use the Python installer for the backend and dependencies,
then build the OS-native Tauri desktop app from `apps/desktop`:

```bash
python3 installer/setup_kattappa.py --accept-agreement
cd apps/desktop
npm install
npm run tauri:build
```

After the native app is built, launch Kattappa through the installer:

```bash
python3 installer/setup_kattappa.py --accept-agreement --launch
```

The launcher starts the backend on `http://127.0.0.1:8000` and opens the built
native desktop app when it is available. On macOS the app bundle is:

```text
apps/desktop/src-tauri/target/release/bundle/macos/Kattappa AI OS.app
```

The browser desktop UI at `http://127.0.0.1:5173` is only a fallback for a fresh
install before the native app has been built. Native Tauri packages must be
built on the target OS because Windows `.exe`, macOS `.app`/`.dmg`, and Linux
AppImage/deb/rpm bundles are OS-specific.

On macOS, setup prepares Kattappa's runtime data under
`~/Library/Application Support/Kattappa AI OS` and runs the Screen Recording
preflight once. Normal desktop opening uses quiet health checks and does not
run project indexing or screen capture until you ask for a task that needs it.

Older root-level wrappers were removed so this project has one setup file and one run executable.

## What Is Built

- Desktop app: Tauri + React at `apps\desktop`
- Backend: FastAPI at `backend\main.py`
- Model router: Ollama at `backend\core\model_router.py`
- Memory: ChromaDB + SQLite at `backend\core\memory.py`
- Agents: planner, memory, safety, evaluator, coder, browser, researcher, desktop, vision, voice, file, terminal, finance, self-improver
- Local Builder Profile: free/local coding-process analytics inspired by builder-profile tools, using only repo structure and git metadata with no transcript or code upload
- Local Creator Tools: free replacements for Pitch/Gamma/Napkin/Headroom/CodeRabbit/GSD/Ralph/MarkItDown/Pomelli/Blackbox-style workflows, including Markdown deck outlines, Mermaid diagrams, local context compression, local code review, plan-execute-verify-fix workflows, document-to-Markdown fallback, and marketing kits
- Local Assistant Patterns: FRIDAY/JARVIS/personal-assistant style voice, screen, memory, and tool routing through Kattappa's desktop app with local-first fallbacks and approval gates
- Finance Brain: OHLCV/K-line forecasting with a local baseline, Kronos readiness status, and baseline-vs-Kronos comparison workflow
- Safety: approval gates, blocked keywords, command allowlist, desktop control off by default

## Finance Brain

Endpoints:

```text
GET  http://127.0.0.1:8000/finance/kronos/status
POST http://127.0.0.1:8000/finance/forecast
POST http://127.0.0.1:8000/finance/forecast-csv
POST http://127.0.0.1:8000/finance/compare
POST http://127.0.0.1:8000/finance/compare-csv
```

The comparison endpoints run the owned local baseline and attempt Kronos on the same validated candles or CSV. If Kronos is missing, not ready, or errors, the response keeps the local baseline, the Kronos readiness details, and the fallback/error details for analysis.

## Safety Defaults

Shell execution is off unless `KATTAPPA_SHELL_ENABLED=true`.

Desktop control is off unless `KATTAPPA_DESKTOP_ENABLED=true`.

Risky actions require approval, including delete, format, payment, send email, submit, purchase, transfer money, password/login actions, registry/security changes, and destructive commands.

## Production Gate

- Keep `setup.bat` as the only setup entrypoint and `run.exe` as the only root run executable.
- Core backend modules must compile before packaging.
- File, terminal, browser, and system-changing actions must route through an approval boundary before execution.
- Memory storage must stay bounded by decay, summarisation, or pruning.
- Generated memory, logs, runtime folders, model downloads, virtual environments, dependency folders, and packaged app outputs must stay untracked.
