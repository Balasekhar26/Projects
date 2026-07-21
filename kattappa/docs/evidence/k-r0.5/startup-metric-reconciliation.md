# Startup Metric Reconciliation Report (K-R0.5)

## Overview

This report reconciles the two observed backend readiness datasets recorded during K-R0.4 implementation and validation.

---

## 1. Dataset Comparison

| Parameter | Dataset A: Full Launcher Evidence | Dataset B: Programmatic DevBackendProcess |
| :--- | :--- | :--- |
| **Recorded Median Readiness** | **21.03 seconds** | **5.50 seconds** |
| **Recorded p95 Readiness** | **22.50 seconds** | **11.92 seconds** |
| **Recorded Max Readiness** | **22.50 seconds** | **14.87 seconds** |
| **Peak Process Tree RSS** | **121.75 MB** | **102.57 MB** |
| **Launcher Command** | `scripts/dev/start_backend.py` | `DevBackendProcess` (dynamic port isolation) |
| **Environment Verification** | Included (`require_verified_environment()`) | Skipped / Direct module import |
| **System Load Context** | Heavy background IDE / Playwright / Frontend | Isolated background subprocess |
| **First Import State** | Cold module import | Warm Python bytecode cache (`__pycache__`) |

---

## 2. Root Cause Analysis of Variance

1. **Environment Verification Overhead**: `scripts/dev/start_backend.py` invokes `require_verified_environment()`, performing workspace root verification, package shadowing checks, and filesystem integrity validation before launching Uvicorn.
2. **Cold vs. Warm Bytecode Cache**: Dataset A runs from a cold process start where Python compiles and imports all standard library and third-party modules. Dataset B runs in an environment where `.pyc` bytecode cache files are already compiled and warm.
3. **Background OS & Process Contention**: Dataset A runs while Uvicorn, Vite dev server, Playwright, and active test suites compete for CPU and disk I/O. Dataset B executes in an isolated environment without active test suite contention.
4. **Endpoint Probe Window**: Dataset A measures the complete round-trip from process spawning to HTTP `/ready` response including Uvicorn socket binding, while Dataset B measures Uvicorn socket readiness directly via lightweight HTTP polling.

---

## 3. Retained Bounds & Standard Operating Procedure

* **Cold Startup Bound**: Retain **30.0 seconds** as the official upper threshold for cold production starts under full launcher validation.
* **Warm / Isolated Start Expectation**: **5.50s - 12.0s** under isolated programmatic execution.
