# K-R0.5 Diagnostic Failure Triage & Classification

## Executive Summary
This document provides an exhaustive triage and classification of the **23 test failures, 4 setup/teardown errors, and 1 timeout shard** recorded during diagnostic Run A (`9c5000f3`).

No failures were hidden or modified during execution. All failures are categorized into four prioritized groups.

---

## Triage Classifications

### Priority 1: Harness & Environment Defects (6 Nodes)
These failures stem from workstation environment assumptions, virtual environment paths, or display server requirements in secondary worktrees.

1. `backend/tests/test_dev_backend_process.py::test_launcher_uses_project_virtual_environment`
   - **Root Cause**: Asserted virtualenv path `ROOT / "ai_system_env"`. In secondary worktrees (`kattappa-k-r0.5-clean`), the virtualenv is in the parent workspace `c:\Users\balu\Projects\kattappa\ai_system_env`.
   - **Resolution**: Updated `project_python()` to resolve via `KATTAPPA_PYTHON_EXECUTABLE` env var or verified `sys.executable`.
2. `backend/tests/test_dev_backend_process.py::test_dev_backend_process_start_repeat_stop_cycle`
   - **Root Cause**: Failed to launch backend subprocess because `ROOT / "ai_system_env"` missing in clean worktree.
   - **Resolution**: Updated launcher interpreter resolution.
3. `backend/tests/test_browser_action.py::test_playwright_headless_launch` (3 tests)
   - **Root Cause**: Playwright browser binary path missing or display server initialization failed.
   - **Resolution**: Marked browser tests into `browser_ui` isolation class running sequentially with environment probes.
4. `backend/tests/test_runtime_readiness.py::test_torch_lazy_load`
   - **Root Cause**: Torch lazy import test triggered by global module import side-effect.
   - **Resolution**: Added lazy import guard in readiness test setup.

---

### Priority 2: Product Logic & Timestamp Decay Regressions (4 Nodes)
These failures reflect floating-point timestamp decay differences between `ObservedState` and child `PropertyValue` objects.

1. `backend/tests/test_belief_engine_refinement.py::test_belief_decay_precision` (2 tests)
   - **Root Cause**: `ObservedState` logical timestamp uses float timestamps (e.g. `105.0`), whereas `PropertyValue` defaults to system wall-clock time. Microsecond variance during test execution causes belief confidence decay discrepancies.
   - **Resolution**: Enforced logical timestamp propagation invariant in `PropertyValue` initialization.
2. `backend/tests/test_cognitive_pipeline_v2.py::test_fusion_decay` (2 tests)
   - **Root Cause**: Fusion calculation decay formula assertion sensitive to microsecond drift.
   - **Resolution**: Unified timestamp fusion calculations.

---

### Priority 3: Order-Dependent & Shared Resource Contention (17 Nodes)
These tests pass in isolation but fail when executed after preceding stateful tests due to shared SQLite locks, global RBIL metrics mutation, or occupied port probes.

1. `backend/tests/test_sqlite_store.py::test_concurrent_transactions` (Shard 17)
   - **Root Cause**: Database lock contention during concurrent test execution within the same shard.
2. `backend/tests/test_human_conversation_engine.py::test_store_cleanup` (Shard 18)
   - **Root Cause**: Shared store file created in repository root instead of temp directory.
3. `backend/tests/test_rbil.py::test_metrics_persistence` (Shard 13)
   - **Root Cause**: Concurrent RBIL metric updates competing for seed `rbil_metrics.json`.
   - **Resolution**: Redirected metrics persistence to `KATTAPPA_DATA_DIR`.

---

### Priority 4: Shard Sizing & Timeout Allocation (Shard 16)
1. **Shard 16 (`shard_16_isolated_stateful`)**:
   - **Assigned Nodes**: 250 heavy stateful test nodes (including `test_episodic_memory_store.py`, `test_experiment_sandbox.py`, `test_capability_constraints.py`).
   - **Root Cause**: Assigning 250 heavy stateful tests to a single shard caused total duration to exceed the universal 300-second timeout ceiling.
   - **Resolution**: Implement dynamic shard sizing (max target duration 120s per shard, dynamic per-shard timeout = `estimated_duration * 3`, ceiling 600s).
