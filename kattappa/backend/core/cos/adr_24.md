# ADR-24: Action Architecture Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Once a planner generates a plan, the execution of actions must be managed safely. Executing actions directly without verification, retry policies, parallel scheduling, or rollback recovery leads to partial failures that corrupt the system's state or leave external tasks in an inconsistent state.

### Decision
Define a robust **Action Architecture** separating planning from acting, managing executions via a transactional action queue.

---

### Core Components & Specs

#### 1. Action Queue & Scheduler
- Actions are scheduled in a priority-based **Action Queue**.
- Supports parallel execution of independent actions (e.g. parallel API queries or file reads) while enforcing sequential locking on dependent actions.

#### 2. Tool Executor & Sandboxing
- Executes tool signatures.
- **Verification Gate**: After an action is executed, a verification check is run to measure outcomes against the expected predicted states.

#### 3. Failure Recovery & Transactional Rollbacks
- **Retry Policy**: Transient failures (e.g. network timeout) trigger exponential backoff retries.
- **Rollback Policy**: If a key action in a multi-step plan fails and cannot be recovered, the Action Executor initiates compensating actions (rollbacks) to revert previous steps (e.g. delete a partially written file or close open network sockets), ensuring system consistency.
