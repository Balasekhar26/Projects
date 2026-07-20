# Hermetic Kattappa Development Environment

Kattappa supports one development import model: execute the repository source
with `C:\Users\balu\Projects\kattappa` as the working tree and
`ai_system_env` as its virtual environment. Do not copy `backend`,
`kattappa_native`, `kattappa_runtime`, `kattappa_data_engine`, or `tests` into
site-packages.

Verify the active environment:

```powershell
ai_system_env\Scripts\python.exe scripts/dev/verify_environment.py
```

Run tests through the guarded runner:

```powershell
ai_system_env\Scripts\python.exe scripts/dev/run_tests.py -q
```

Create or repair the pinned environment:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev/bootstrap_environment.ps1
```

To rebuild it explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev/bootstrap_environment.ps1 -Recreate
```

The verifier is diagnostic-only. It exits non-zero and prints conflicting
locations; it never removes packages or mutates the environment.

Normal development startup remains non-blocking:

```powershell
ai_system_env\Scripts\python.exe scripts/dev/start_backend.py
```

Only validation sandboxes that require a foreground parent should use:

```powershell
ai_system_env\Scripts\python.exe scripts/validation/run_backend_foreground.py
```
