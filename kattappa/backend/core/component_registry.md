# Kattappa Cognitive Component Inventory

This registry tracks the core cognitive subsystems, files, dependencies, tests, and metadata values of Project Kattappa to maintain codebase integrity and prevent structural duplication.

---

## 1. Governance & Permissions

### Permission & Safety Governor
* **Target File:** [permission_governor.py](file:///c:/Users/balu/Projects/kattappa/backend/core/governance/permission_governor.py)
* **Purpose:** Runs execution authorization pipelines checking capability registry settings, path policy constraints, command safety variables, and human approval limits.
* **Owner:** governance
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** None
* **Security Critical:** Yes (High)
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `CapabilityRegistry`, `PolicyEngine`, `SafetyMonitor`
* **Test File:** [test_permission_governor.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_permission_governor.py)

### Capability Registry
* **Target File:** [capability_registry.py](file:///c:/Users/balu/Projects/kattappa/backend/core/capability_registry.py)
* **Purpose:** Manages thread-safe dynamic allowlists/denylists mapping agent identities to privilege sets (e.g. `CAP_FILE_WRITE`), including support for session context overrides.
* **Owner:** governance
* **Stability:** Stable
* **Thread Safety:** Yes (via threading.RLock)
* **Async Safe:** Yes
* **Persistence Layer:** JSON
* **Security Critical:** Yes (High)
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `threading`
* **Test File:** [test_tool_acquisition.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_tool_acquisition.py)

### Policy Engine
* **Target File:** [policy_engine.py](file:///c:/Users/balu/Projects/kattappa/backend/core/governance/policy_engine.py)
* **Purpose:** Validates tool path boundaries, restricted subfolders, network settings, and validation flags.
* **Owner:** governance
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** JSON Config
* **Security Critical:** Yes (High)
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `pathlib`
* **Test File:** [test_observability_governance.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_observability_governance.py)

### Safety Monitor
* **Target File:** [safety_monitor.py](file:///c:/Users/balu/Projects/kattappa/backend/core/governance/safety_monitor.py)
* **Purpose:** Scans shell command payloads and script contents for unsafe modifiers, forbidden binaries, and injection markers.
* **Owner:** governance
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** None
* **Security Critical:** Yes (High)
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `re`
* **Test File:** [test_observability_governance.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_observability_governance.py)

### Audit Ledger
* **Target File:** [audit_ledger.py](file:///c:/Users/balu/Projects/kattappa/backend/core/governance/audit_ledger.py)
* **Purpose:** Captures SHA-256 argument hashes, decision logs, reasons, timestamps, and session variables, persisting them to JSON format database tables.
* **Owner:** governance
* **Stability:** Stable
* **Thread Safety:** Yes (via threading.Lock)
* **Async Safe:** Yes
* **Persistence Layer:** JSON
* **Security Critical:** Yes (High)
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `hashlib`, `json`, `threading`
* **Test File:** [test_audit_ledger.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_audit_ledger.py)

---

## 2. Planning & World Models

### World Model Engine
* **Target File:** [world_model.py](file:///c:/Users/balu/Projects/kattappa/backend/core/planning/world_model.py)
* **Purpose:** Simulates variable state modifications, resource budget depletions, timestamp increments, and multi-step trajectory feasibility projections.
* **Owner:** planning
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** None
* **Security Critical:** No
* **Performance Critical:** Yes
* **External Dependencies:** None
* **Dependencies:** None
* **Test File:** [test_world_model.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_world_model.py)

### Meta-Cognition Engine
* **Target File:** [meta_cognition.py](file:///c:/Users/balu/Projects/kattappa/backend/core/planning/meta_cognition.py)
* **Purpose:** Tracks self-awareness states, calibrates uncertainty ratings, adjusts compute token allocations, checks introspection bounds, and routes dynamic planners.
* **Owner:** planning
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** None
* **Security Critical:** No
* **Performance Critical:** Yes
* **External Dependencies:** None
* **Dependencies:** None
* **Test File:** [test_meta_cognition.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_meta_cognition.py)

### Goal Manager
* **Target File:** [goal_manager.py](file:///c:/Users/balu/Projects/kattappa/backend/core/goal_manager.py)
* **Purpose:** Coordinates task scheduling, dependency checks, suspend/resume serialization snapshot cycles, and exponential retry backoffs.
* **Owner:** planning
* **Stability:** Stable
* **Thread Safety:** Yes (database level locks)
* **Async Safe:** Yes
* **Persistence Layer:** SQLite (goal_memory.db)
* **Security Critical:** Medium
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `GoalMemory`, `WORKSPACE`
* **Test File:** [test_goal_manager.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_goal_manager.py)

---

## 3. Sandboxing & Isolation

### Local Execution Sandbox
* **Target File:** [local_sandbox.py](file:///c:/Users/balu/Projects/kattappa/backend/core/sandbox/local_sandbox.py)
* **Purpose:** Executes commands in separate process groups, kills process trees recursively on timeouts, and reverts directory file modifications using copy-on-write snapshot backups.
* **Owner:** sandbox
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** Temp Directory
* **Security Critical:** Yes (High)
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `subprocess`, `shutil`, `tempfile`
* **Test File:** [test_local_sandbox.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_local_sandbox.py)

### Execution Sandbox Runtime (Unified)
* **Target File:** [sandbox_runtime_unified.py](file:///c:/Users/balu/Projects/kattappa/backend/core/sandbox/sandbox_runtime_unified.py)
* **Purpose:** Provides unified wrapper calls (`execute_tool`, `execute_shell`, `execute_python`, `execute_workflow`) with permission validation checks, env secret scrubbing, sandboxed execution, and audit log records.
* **Owner:** sandbox
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** Temp Directory, JSON logs
* **Security Critical:** Yes (High)
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `PermissionGovernor`, `SecretBroker`, `LocalExecutionSandbox`, `AuditLedger`
* **Test File:** [test_sandbox_runtime_unified.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_sandbox_runtime_unified.py)

### Sandbox Manager (Docker)
* **Target File:** [sandbox_manager.py](file:///c:/Users/balu/Projects/kattappa/backend/core/sandbox/sandbox_manager.py)
* **Purpose:** Coordinates Docker container runs, mapping directories, resource profile shares, and network interfaces.
* **Owner:** sandbox
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** Docker Engine
* **Security Critical:** Yes (High)
* **Performance Critical:** No
* **External Dependencies:** Docker Daemon / Podman
* **Dependencies:** Docker runtime, `subprocess`
* **Test File:** [test_cognitive_simulation_sandbox.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_cognitive_simulation_sandbox.py)

---

## 4. Communication & Messaging

### Event Bus
* **Target File:** [event_bus.py](file:///c:/Users/balu/Projects/kattappa/backend/core/event_bus.py)
* **Purpose:** Decoupled publisher-subscriber messaging enabling thread-safe asynchronous notification dispatches and SQLite audit logging.
* **Owner:** communication
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** SQLite (event_ledger.db)
* **Security Critical:** Medium
* **Performance Critical:** Yes
* **External Dependencies:** None
* **Dependencies:** `sqlite3`, `concurrent.futures`
* **Test File:** [test_event_bus.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_event_bus.py)

### Cognitive Blackboard
* **Target File:** [blackboard.py](file:///c:/Users/balu/Projects/kattappa/backend/core/blackboard.py)
* **Purpose:** Decoupled global blackboard workspace routing and typed session-scoped Facts, Assumptions, and Constraints registers.
* **Owner:** communication
* **Stability:** Stable
* **Thread Safety:** Yes (via threading.RLock and Lock)
* **Async Safe:** Yes
* **Persistence Layer:** Memory
* **Security Critical:** Medium
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `threading`, `uuid`
* **Test File:** [test_blackboard.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_blackboard.py)

---

## 5. Agent Society & Runtimes

### Agent Runtime
* **Target File:** [agent_runtime.py](file:///c:/Users/balu/Projects/kattappa/backend/core/agent_runtime.py)
* **Purpose:** Coordinates live running instances of agent specialists, triggering sandboxed commands, creating task goals, and writing observations.
* **Owner:** orchestrator
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** None
* **Security Critical:** Yes (High)
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `EventBus`, `BLACKBOARD`, `GoalManager`, `LocalExecutionSandbox`
* **Test File:** [test_agent_runtime.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_agent_runtime.py)

### Multi-Agent Orchestrator
* **Target File:** [multi_agent_orchestrator.py](file:///c:/Users/balu/Projects/kattappa/backend/core/orchestrator/multi_agent_orchestrator.py)
* **Purpose:** Coordinates prompt routing, dynamic agent spawning, blackboard postings, consensus debate triggers, and reputation updates on outcomes.
* **Owner:** orchestrator
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** None
* **Security Critical:** Yes (High)
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `DEFAULT_ROUTER`, `DEFAULT_REGISTRY`, `Agent`, `AgentSociety`, `BLACKBOARD`, `EventBus`, `GoalManager`
* **Test File:** [test_multi_agent_orchestrator.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_multi_agent_orchestrator.py)

### Executive Controller
* **Target File:** [executive_controller.py](file:///c:/Users/balu/Projects/kattappa/backend/core/cos/executive_controller.py)
* **Purpose:** Central OS scheduler tick loop coordinating perceive, retrieve, reason, plan, act, and learn steps, handling high-priority interrupts, and allocating budgets.
* **Owner:** orchestrator
* **Stability:** Stable
* **Thread Safety:** Yes (via threading.Lock)
* **Async Safe:** Yes
* **Persistence Layer:** None
* **Security Critical:** Yes (High)
* **Performance Critical:** Yes
* **External Dependencies:** None
* **Dependencies:** `threading`, `time`
* **Test File:** [test_executive_controller.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_executive_controller.py)

---

## 6. Skill Ecosystem & Learning

### Skill Runtime
* **Target File:** [skill_runtime.py](file:///c:/Users/balu/Projects/kattappa/backend/core/skill_runtime.py)
* **Purpose:** Represents executable skill objects containing parameters validations, shlex command builders, sandboxed executions, and trust metrics record updates.
* **Owner:** learning
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** JSON templates (`skills.json`)
* **Security Critical:** Yes (High)
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** `EventBus`, `LocalExecutionSandbox`, `SkillLibrary`
* **Test File:** [test_skill_runtime.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_skill_runtime.py)

### Skill Discovery Engine
* **Target File:** [skill_discovery.py](file:///c:/Users/balu/Projects/kattappa/backend/core/skill_discovery.py)
* **Purpose:** Evaluates matching skill templates, verifying tool prerequisite coverage against sandbox environments, and ranking candidates based on trust priorities and success rates.
* **Owner:** learning
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** None
* **Security Critical:** Medium
* **Performance Critical:** Yes
* **External Dependencies:** None
* **Dependencies:** `SkillLibrary`, `SkillGraph`
* **Test File:** [test_skill_discovery.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_skill_discovery.py)

### Skill Composer
* **Target File:** [skill_composer.py](file:///c:/Users/balu/Projects/kattappa/backend/core/skill_composer.py)
* **Purpose:** Compiles multiple constituent skills into executable ComposedSkill DAGs. Provides dependency validation, DFS cycle detection, topological layer partitioning (Kahn's algorithm), critical-path latency estimation, total cost estimation, and fallback plan binding.
* **Owner:** learning
* **Stability:** Stable
* **Thread Safety:** Yes
* **Async Safe:** Yes
* **Persistence Layer:** None
* **Security Critical:** No
* **Performance Critical:** No
* **External Dependencies:** None
* **Dependencies:** None
* **Test File:** [test_skill_composer.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_skill_composer.py)

### Workflow Runtime
* **Target File:** [workflow_runtime.py](file:///c:/Users/balu/Projects/kattappa/backend/core/workflow_runtime.py)
* **Purpose:** Executes ComposedSkill DAGs produced by SkillComposer. Supports per-node retry policies with exponential backoff, per-node timeouts, intra-layer concurrent execution (ThreadPoolExecutor), fallback skill invocation, SQLite checkpoint persistence, workflow resumption, and full EventBus integration for lifecycle events (WorkflowStarted/Completed/Failed/NodeStarted/NodeSucceeded/NodeFailed/NodeRetrying/NodeSkipped/CheckpointSaved).
* **Owner:** learning
* **Stability:** Stable
* **Thread Safety:** Yes (via threading.Lock + ThreadPoolExecutor)
* **Async Safe:** Yes
* **Persistence Layer:** SQLite (`workflow_checkpoints.db`)
* **Security Critical:** No
* **Performance Critical:** Yes
* **External Dependencies:** None
* **Dependencies:** `EventBus`, `SkillComposer`, `SkillRuntime`
* **Test File:** [test_workflow_runtime.py](file:///c:/Users/balu/Projects/kattappa/backend/tests/test_workflow_runtime.py)
