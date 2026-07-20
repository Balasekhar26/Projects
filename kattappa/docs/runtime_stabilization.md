# Runtime Stabilization Contract

This document defines the production contract for Kattappa's semantic response
cache and Windows development-backend lifecycle.

## Semantic response cache

`backend.core.semantic_cache.SemanticResponseCache` has two independent layers:

1. A normalized-query SQLite cache, which is persistent and always queried
   first.
2. A Chroma semantic index configured with
   `KattappaCacheEmbeddingFunction`, an explicit adapter over Kattappa's RAG
   embedding engine.

Chroma's `DefaultEmbeddingFunction` is not used. If Chroma or the local
embedding model is unavailable, exact cache reads and writes continue. The
failure is logged as `semantic_response_cache_degraded`, and `/ready` reports
the active mode and reason under `semantic_cache`.

The supported modes are:

- `semantic`: semantic and exact matching are active.
- `exact_match_with_lazy_semantic`: exact matching is active and the semantic
  provider has not yet been loaded.
- `exact_match_fallback`: exact matching is active after a recorded semantic
  provider failure.

## Backend lifecycle

The authoritative runtime directory is:

```text
.kattappa/runtime/
├── backend.state.json
├── backend.pid
├── backend.port
└── backend.log
```

State, PID, and port files are written atomically. A recorded PID is accepted
only when its creation time, working directory, command line, Git checkout,
and listening port match the Kattappa backend. An occupied port whose owner
cannot be identified is never terminated.

Start and stop are idempotent:

```powershell
ai_system_env\Scripts\python.exe scripts\dev\start_backend.py --port 8000
ai_system_env\Scripts\python.exe scripts\dev\start_backend.py --port 8000
ai_system_env\Scripts\python.exe scripts\dev\stop_backend.py
ai_system_env\Scripts\python.exe scripts\dev\stop_backend.py
```

Repeated start returns the existing healthy process. Repeated stop reports
that the backend is already stopped. Failed startup terminates the owned
process tree and removes all state files.

`/health` is a fast process-liveness endpoint. It deliberately does not probe
Ollama or enumerate models. `/ready` reports capability readiness. Expensive
maintenance schedulers and model warm-up start only after ASGI readiness, so
they cannot block the launcher.

PyTorch-backed GPU profiling and the custom voice-model architecture are also
lazy-loaded. Registering the HTTP and WebSocket routes does not import PyTorch;
this preserves cold-start margin while leaving those capabilities available on
first use.

## Interpreter contract

Development launchers resolve the interpreter explicitly from:

```text
ai_system_env\Scripts\python.exe
```

They do not use `python`, `py`, or `sys.executable` inherited from a global
shell. Tests verify that the suite itself is running in a virtual environment
and that the launcher resolves the project venv.

The current local `ai_system_env` was created from CPython 3.13.13. Rebuilding
that environment on CPython 3.10 is an operator/environment migration and was
not performed by this source-code stabilization change. Until that migration
is scheduled, the important enforced boundary is that Kattappa consistently
uses its project venv rather than the global interpreter.

## Verification

Focused release-gate command:

```powershell
$env:KATTAPPA_TEST_MODE = "true"
ai_system_env\Scripts\python.exe -m pytest `
  backend/tests/test_adaptive_runtime.py `
  backend/tests/test_runtime_readiness.py `
  backend/tests/test_dev_backend_process.py `
  backend/tests/test_finance_brain.py -q
```

The focused gate must pass three consecutive times before the full suite is
accepted.

## Validation evidence and exhaustive-suite status

The stabilization gate passed three consecutive cold-process runs at 35/35.
The final affected-subsystem lane passed 62/62, and the configured native,
data-engine, and resource-governor roots passed 85/85.

Collection currently contains 3,171 tests. The monolithic exhaustive command
did not complete inside a 15-minute bound, and the backend-only non-slow lane
did not complete inside a 20-minute bound. Verbose diagnosis exposed two
pre-existing benchmark regressions (protected desktop application dispatch and
website-download planner chaining); both were fixed and their 9-test module is
green. The remaining 3,000+ backend inventory has not produced a terminal
all-green result in this engineering session, so it must not be reported as a
full-suite pass. It should be executed by Antigravity with a longer monitored
runtime or split into persisted test-manifest shards.
