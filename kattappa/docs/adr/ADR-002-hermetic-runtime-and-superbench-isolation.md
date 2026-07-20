# ADR-002: Hermetic Runtime and Superbench Isolation

## Status

Accepted for K-R0.4.

## Context

A copied `backend` directory in the virtual environment previously shadowed
the active workspace. Superbench also stored execution results in the shared
application database and had no run-scoped vector state or structured failure
contract. A historical native `loadIndex` allocation failure was reported, but
the original index and exception evidence were not preserved, so its exact
cause cannot be reconstructed safely.

## Decisions

1. Development uses one explicit **workspace source path** model. Kattappa is
   not installed as a wheel or copied package because this repository has no
   Python build metadata. Every supported launcher verifies that first-party
   imports resolve under the active repository and that no duplicate package or
   `tests` directory exists in site-packages.
2. `scripts/dev/bootstrap_environment.ps1` is the supported create/repair
   command. It installs `requirements.lock.txt`, verifies provenance, and
   collects the suite. Runtime code never deletes a conflicting installation.
3. The normal backend launcher is non-blocking. Foreground behavior belongs to
   `scripts/validation/run_backend_foreground.py`.
4. `/health` does not inspect memory or providers. `/ready` reports availability
   without loading Torch, Chroma, ONNX Runtime, Transformers, Kronos weights, or
   local LLMs.
5. The default backend readiness timeout remains 30 seconds. Ten clean starts
   measured readiness between 18.820 and 22.497 seconds, median 21.030 seconds,
   p95 22.497 seconds, with peak sampled RSS 121,753,600 bytes. A 30-second
   bound provides more than 33% headroom over the observed maximum.
6. Superbench defaults to isolated memory. Each run owns a separate workspace,
   SQLite source, vector index, manifest, diagnostics, run ID, and trace ID.
   Production memory requires explicit authorization.
7. Vector failures are recorded before recovery. The original index is renamed
   into quarantine, never deleted. Rebuild occurs from authoritative SQLite
   data, is verified, and is switched atomically. The current run remains
   explicitly degraded and uses keyword fallback even when recovery succeeds.

## Consequences

- Backend startup no longer imports all memory stores; the public memory module
  uses lazy exports.
- Existing implicit memory migration copies data but never deletes the source.
- Benchmark records persist in a dedicated Superbench database rather than the
  production memory database.
- Historical `loadIndex` root cause remains unknown because earlier validation
  deleted the relevant data. New diagnostics make future failures attributable.

## Evidence

Machine-readable timing evidence is stored in
`docs/evidence/backend_startup_measurements.json`.
