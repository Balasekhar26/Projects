# K-R0.4 Implementation Report

## Status

Engineering implementation is complete and the focused acceptance gates pass.
The milestone is **not release-validated** because the monolithic 3,192-test
suite exceeded its fixed one-hour bound, and Antigravity has not yet performed
the required independent validation.

## 1. Root cause

The original validation mixed four faults:

1. A copied first-party package in site-packages could shadow the workspace and
   change test discovery.
2. Backend startup eagerly imported semantic-memory dependencies, including
   Chroma/ONNX paths, even when readiness did not need them.
3. Superbench shared application storage and did not persist a canonical
   run/trace/failure contract.
4. The historical native `loadIndex` failure cannot be diagnosed exactly
   because its index was deleted before evidence was captured.

Desktop acceptance also found a stale statistics-column reference and a
pre-existing browser provenance bug: unknown domains inherited the generic
adapter's 95/100 trust score rather than the domain classifier's 70/100 score.

## 2. Architecture decision

- Use an explicit workspace-source import model guarded before development
  startup and test collection.
- Keep the normal backend launcher non-blocking; use a validation-only
  foreground launcher when a parent process must remain attached.
- Keep readiness lightweight and all heavy ML/index providers lazy.
- Persist Superbench records in a dedicated database and give every run its own
  workspace, authoritative SQLite source, vector state, manifest, diagnostics,
  run ID, and trace ID.
- Default to isolated memory. Production memory requires explicit
  authorization.
- Quarantine failed indexes, rebuild from authoritative data, verify, and
  switch atomically. Never delete the original index automatically.
- Degrade explicitly to keyword retrieval when vector retrieval is unavailable.

## 3. Files changed

The implementation affects:

- environment guards and launchers under `scripts/dev/` and
  `scripts/validation/`
- root pytest provenance enforcement in `conftest.py`
- lazy memory exports and non-destructive legacy migration
- readiness and backend-process startup telemetry
- Superbench engine, API, memory session, vector resilience, and isolated worker
- desktop Superbench API client and telemetry panel
- K-R0.4 regression and integration tests under `backend/tests/`
- this ADR, environment guide, startup evidence, and UI screenshot
- an existing browser broker trust propagation defect found by the broad suite

## 4. Packaging strategy

Selected strategy: `workspace_source_path`.

The repository has no Python package build metadata suitable for a supported
editable or wheel installation. The verifier inserts and validates the current
repository root, rejects copied duplicates in site-packages, and never mutates
the environment. `scripts/dev/bootstrap_environment.ps1` creates or repairs
the pinned virtual environment and performs provenance verification plus test
collection.

## 5. Startup measurements

Ten clean cold starts produced:

| Metric | Seconds |
| --- | ---: |
| Minimum `/health` | 18.800 |
| Median `/health` | 21.010 |
| Maximum `/health` / p95 | 22.479 |
| Minimum `/ready` | 18.820 |
| Median `/ready` | 21.030 |
| Maximum `/ready` / p95 | 22.497 |

Peak sampled RSS was 121,753,600 bytes. No Torch, Chroma, ONNX Runtime,
Transformers, Kronos, or local-LLM module was loaded by readiness. The retained
default bound is 30 seconds. One later manual restart while the desktop,
Playwright, and development server were active reported 30.202 seconds, so
contention remains an explicit independent-validation risk rather than a reason
to inflate the timeout without a new clean measurement set.

Machine-readable measurements are in
`docs/evidence/backend_startup_measurements.json`.

## 6. Vector-index diagnosis

The historical failure remains unknowable because its evidence was deleted.
The controlled isolated failure proves the new diagnostic contract:

- exception: `builtins.MemoryError`
- message: `controlled loadIndex memory-allocation failure`
- fingerprint: `ffabdfbbf22e93628e72054c`
- collection: `superbench_run_memory`
- embedding: `kattappa_deterministic` / `sha256-token-v1` / dimension 32
- backend version: 1
- process RSS: 108,515,328 bytes
- available RAM: 4,422,344,704 bytes
- open clients/readers/writers: 3/1/0
- opened elsewhere: false
- memory mode: isolated

The full traceback and storage measurements were persisted before recovery.

## 7. Migration and quarantine

Implicit legacy migration now copies source data and never deletes it.
The controlled failure renamed the 1,078-byte original index to:

`vector_index.quarantine.20260720T130243598302Z`

The authoritative SQLite source was 12,288 bytes. A rebuilt index was verified
and atomically activated. The triggering run remained `degraded` and used
`keyword_fallback`; recovery did not rewrite the result as a full success.

## 8. Automated validation

- Environment verifier: pass; all four first-party imports resolve under the
  workspace and no stale `tests` package is present.
- Ruff on the new K-R0.4 modules: pass. The legacy `action_broker.py`
  still has seven pre-existing unused-import/local warnings when linted as a
  whole; the trust-propagation change adds no new Ruff finding.
- Desktop production build: pass (Vite, 37 modules).
- Expanded targeted gate, clean backend state, three consecutive runs:
  - 32 passed in 87.27s
  - 32 passed in 103.11s
  - 32 passed in 68.99s
- Collection: 3,192 tests in 77.24s.
- Monolithic full suite: **timed out after 3,604s, exit 124; no final pytest
  summary, therefore not a pass**.
- Supported non-backend testpaths: 85 passed in 137.05s.
- First 40-file backend diagnostic shard: 544 passed and 3 failed in 749.24s.
  The browser trust failure was corrected and its focused test now passes. The
  two belief-confidence tests pass alone and exhibit order/time-sensitive
  tolerance drift in the broad shard; their design requires separate
  architectural/test determinism work and was not weakened here.

## 9. Manual API and UI evidence

Normal direct API runs:

| Run ID | Trace ID | Status | Duration | Backend |
| --- | --- | --- | ---: | --- |
| `sb_run_b861dcbe144648d08223c1dd30d23392` | `sb_trace_d6b0776aecbe4937ad5cc70b2aba4342` | succeeded | 0.065s | isolated_vector |
| `sb_run_93d28a0dc1cd47aba53a827c4c84e92c` | `sb_trace_56b9d73adf0b4d638e18557e3b9629a2` | succeeded | 0.064s | isolated_vector |
| `sb_run_f42d4a5f5ad04ac581e30ce43ab4d3b9` | `sb_trace_90a227563113455f8bf757ce5672469e` | succeeded | 0.071s | isolated_vector |

After restart, the first historical record remained retrievable and a new run
`sb_run_1134743b4e834037a0e3ffff7e4d8562` /
`sb_trace_ddf7840b1b2e4fb5b39f00bb3d509a0c` succeeded in 0.082s.

The desktop panel triggered run
`sb_run_c8644e7fc1da4009a99fb7d93392e953` with trace
`sb_trace_e8f46d13f20d46d7b533dc24587999a5`; the UI and API record agree,
status is `succeeded`, duration is 0.186s, and memory is
`isolated / isolated_vector`. Evidence:
`output/playwright/k-r0.4-superbench-ui-success.png`.

Controlled vector failure run
`sb_run_77ad6d6dd6894996867e2f3723a0ccdd` degraded in 0.107s with
`VECTOR_INDEX_LOAD_FAILURE`, keyword fallback, fingerprint
`ffabdfbbf22e93628e72054c`, and recovery action `recovered`.

Vector-disabled run `sb_run_89f0cb8a0ce44789b4cb7bb64262a725` degraded in
0.063s with keyword fallback and an explicit warning.

## 10. Remaining risks

1. The monolithic full suite did not complete within one hour and therefore
   does not satisfy the release gate.
2. Belief confidence tests use time-sensitive calculations with very narrow
   tolerances and can fail in broad/order-dependent execution while passing in
   isolation.
3. A contended manual backend start reached 30.202 seconds even though the ten
   clean measurements remain below 22.5 seconds.
4. The historical deleted vector index cannot be retrospectively diagnosed.
5. Antigravity independent validation is still required.
6. The legacy action broker retains seven unrelated Ruff findings that should
   be handled in a dedicated cleanup rather than mixed into this runtime gate.

## 11. Release statement

K-R0.4 is implemented and ready for independent validation, but it is **not
release-ready**. The full-suite gate did not pass, and Capability and Permission
Management must not begin until the outstanding validation criteria are closed.
