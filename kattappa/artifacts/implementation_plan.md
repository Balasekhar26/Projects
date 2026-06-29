# Implementation Plan: Goal Manager & Memory Fabric Partitions

This plan outlines the design and technical steps for implementing the **Goal Manager** process scheduler, partitioning the **Cognitive Memory Fabric** into its 8 dedicated subsystems, resolving the broken test, and refactoring the React dashboard UI.

---

## User Review Required

> [!IMPORTANT]
> **SQLite WAL Concurrency Locks**: With parallel write processes from the Goal Manager, Agent Tasks, and Memory Consolidation running, we must ensure connection locking. All SQLite connections will utilize Write-Ahead Logging (WAL) and busy timeouts of 30 seconds.

> [!WARNING]
> **Act-R Forgetting & Eviction**: Activation-based memory decay will automatically migrate low-activation episodic items to cold storage. Pinned memories or goals bypass decay.

---

## Open Questions

> [!NOTE]
> *   **Q1**: Should low-priority active goals be automatically suspended immediately upon a higher-priority goal entering the queue, or should we allow a grace time (e.g. 5 seconds) for the current tick to conclude cleanly?
>     *   *Proposed Answer*: Suspend immediately on the next tick boundaries during the scheduler's check loop to prevent unwanted execution resource usage on lower-priority items.
> *   **Q2**: What should be the default retry policy for failed goals?
>     *   *Proposed Answer*: Max 3 retries, using exponential backoff ($2^n \times 1\text{s}$) with jitter.

---

## Proposed Changes

### Component 1: Test Suite Stabilization

Fix the type conversion and attribute access mismatch in the Cognitive OS integration test.

#### [MODIFY] [test_cognitive_os.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/tests/test_cognitive_os.py)
*   Update `test_cognitive_kernel_routing` to assert `events_triggered[0]["payload"]["data"] == "ok"` instead of accessing `.payload` directly, aligning with the dict callback type.

---

### Component 2: Goal Manager & Process Scheduler

Upgrade `GoalManager` to act as a topological process scheduler (differentiating from the static Pydantic registry).

#### [MODIFY] [goal_manager.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/goal_manager.py)
*   **Topological Queueing**: Implement a scheduling queue that resolves goal topological dependencies. Only goals whose dependencies are `COMPLETED` can transition to `ACTIVE`.
*   **Goal Suspend & Snapshot Resume**: Implement `suspend(goal_id: str)` and `resume(goal_id: str)`. When a higher-priority goal starts, lower-priority active goals transition to `PAUSED`/`SUSPENDED`. The workspace state (scratchpad/reasoning stack registers) is serialized and persisted. Resuming restores these registers.
*   **Retry Policy & Backoff**: Add retry tracking (fields: `retry_count`, `max_retries`, `last_attempt_at`, `backoff_delay_sec`). If a goal fails, the scheduler checks if `retry_count < max_retries`, waits for backoff, and automatically retries.
*   **Ledger Integration**: Log all state changes (proposed, suspended, active, completed, retried) to `KERNEL.ledger` as events.

#### [MODIFY] [goal_hierarchy.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/goal_hierarchy.py)
*   Update database schema and class model to support `max_retries`, `retry_count`, `last_attempt_at`, `backoff_delay`, `priority_score` (computed dynamically), and `workspace_snapshot_json` for task state serialization.

#### [MODIFY] [test_goal_manager.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/tests/test_goal_manager.py)
*   Add tests for:
    *   Topological order scheduling (blocking goals with unmet dependencies).
    *   Goal suspension and workspace register snapshot serialization/restoration.
    *   Exponential backoff retries.
    *   Execution Ledger logs.

---

### Component 3: Cognitive Memory Fabric Partitions

Implement distinct memory partitions under `CognitiveMemoryBus`.

#### [NEW] [memory_object.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/memory_object.py)
*   Define the unified `MemoryObject` data model matching ADR-03 (immutable `memory_id`, `revision_id`, `parent_revision`, `system_type`, content, belief confidence, Act-R activation parameters, tags).

#### [NEW] [preference_memory.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/preference_memory.py)
*   Implement `PreferenceMemory` subsystem tracking user profile/habit preferences. Includes:
    *   *SQLite Store*: Schema with confidence ratings, evidence counts, and states.
    *   *Retrieval Strategy*: Quick key-value and semantic category lookups.
    *   *Aging Policy*: Evicts low-confidence or superseded values.
    *   *Ledger*: Records updates to the execution ledger.

#### [MODIFY] [cognitive_memory_bus.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/cognitive_memory_bus.py)
*   Update the read/write routers to support all 8 memory partitions: Episodic, Semantic, Procedural, Preference, Relationship, Goal, Belief Graph, and Knowledge Graph.
*   Enforce Act-R activation score calculations on retrieval:
    $$\text{RecallScore} = w_1 \cdot \text{Similarity} + w_2 \cdot \text{Activation} + w_3 \cdot \text{RecencyDecay}$$

#### [NEW] [test_preference_memory.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/tests/test_preference_memory.py)
*   Add unit tests for preference creation, retrieval, and evidence-based reinforcement.

---

### Component 4: Monolithic React UI Decomposition

Refactor the React dashboard frontend.

#### [NEW] [MemoryPanel.tsx](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/dashboard/src/components/MemoryPanel.tsx)
*   Extract memory searches, vector listings, and detail views from App.tsx.

#### [NEW] [TasksPanel.tsx](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/dashboard/src/components/TasksPanel.tsx)
*   Extract Goal/Task tree representation and status views.

#### [NEW] [LedgerPanel.tsx](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/dashboard/src/components/LedgerPanel.tsx)
*   Extract execution events timelines and parent/child DAG traversal views.

#### [MODIFY] [App.tsx](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/dashboard/src/App.tsx)
*   Refactor to import and mount the decomposed panel components, serving as a clean navigation router.

---

## Verification Plan

### Automated Tests
*   Verify the test suite fix:
    ```bash
    ./ai_system_env/bin/python3 -m pytest backend/tests/test_cognitive_os.py
    ```
*   Verify the Goal Manager tests:
    ```bash
    ./ai_system_env/bin/python3 -m pytest backend/tests/test_goal_manager.py
    ```
*   Verify the Preference Memory tests:
    ```bash
    ./ai_system_env/bin/python3 -m pytest backend/tests/test_preference_memory.py
    ```
*   Run the complete test suite:
    ```bash
    ./ai_system_env/bin/python3 -m pytest backend/tests
    ```

### Manual Verification
*   Compile the Vite production build:
    ```bash
    cd dashboard
    npm run build
    ```
