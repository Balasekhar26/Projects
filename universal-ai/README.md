# Universal AI / Sekhar AI OS Max

Fully free, local-first Windows desktop AI OS.

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
run.exe stop       # stop services started by Universal AI
```

Older root-level wrappers were removed so this project has one setup file and one run executable.

## What Is Built

- Desktop app: Tauri + React at `apps\desktop`
- Backend: FastAPI at `backend\main.py`
- Model router: Ollama at `backend\core\model_router.py`
- Memory: ChromaDB + SQLite at `backend\core\memory.py`
- Agents: planner, memory, safety, evaluator, coder, browser, researcher, desktop, vision, voice, file, terminal, finance, self-improver
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

Shell execution is off unless `SEKHAR_SHELL_ENABLED=true`.

Desktop control is off unless `SEKHAR_DESKTOP_ENABLED=true`.

Risky actions require approval, including delete, format, payment, send email, submit, purchase, transfer money, password/login actions, registry/security changes, and destructive commands.
