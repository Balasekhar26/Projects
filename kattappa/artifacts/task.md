# Task Checklist: Goal Manager & Memory Fabric Partitions

- `[x]` **Phase 1: Test Suite Stabilization**
  - `[x]` Fix the dictionary-to-object attribute mismatch in `test_cognitive_kernel_routing` inside [test_cognitive_os.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/tests/test_cognitive_os.py)
  - `[x]` Run specific test to verify it passes cleanly

- `[x]` **Phase 2: Goal Manager & Process Scheduler**
  - `[x]` Update database schema in [goal_memory.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/goal_memory.py) to include retry and snapshot attributes
  - `[x]` Implement topological queue scheduling, task suspension workspace state snapshots, and retry backoff policies in [goal_manager.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/goal_manager.py)
  - `[x]` Write comprehensive unit tests for scheduling, suspension, and retries in [test_goal_manager.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/tests/test_goal_manager.py)

- `[x]` **Phase 3: Cognitive Memory Fabric Partitions**
  - `[x]` Create [memory_object.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/memory_object.py) defining the canonical `MemoryObject` dataclass
  - `[x]` Implement [preference_memory.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/preference_memory.py) with SQLite storage, aging, and retrieval
  - `[x]` Integrate 8 distinct subsystems and Act-R activation scoring in [cognitive_memory_bus.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/cognitive_memory_bus.py)
  - `[x]` Create unit tests for Preference Memory in [test_preference_memory.py](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/tests/test_preference_memory.py)

- `[x]` **Phase 4: Monolithic React UI Decomposition**
  - `[x]` Create decomposed panels [MemoryPanel.tsx](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/dashboard/src/components/MemoryPanel.tsx), [TasksPanel.tsx](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/dashboard/src/components/TasksPanel.tsx), and [LedgerPanel.tsx](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/dashboard/src/components/LedgerPanel.tsx)
  - `[x]` Clean [App.tsx](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/dashboard/src/App.tsx) to act as a tab router
  - `[x]` Verify clean production building of frontend assets
