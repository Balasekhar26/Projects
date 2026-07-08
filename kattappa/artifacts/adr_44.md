# ADR-44: Disaster Recovery & Fault Tolerance Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Running long-horizon cognitive cycles exposes Kattappa to execution disruptions: API timeouts, network cuts, system power failures, or memory corruption. If the system crashes mid-plan, the workspace must not be left corrupted, and the agent must be able to restore its state.

### Decision
Define a robust **Fault Tolerance & Disaster Recovery** model that guarantees transaction rollback, state snapshots, and graceful degraded execution.

---

### Core Specifications

#### 1. State Serialization & Snapshots
- The Executive Controller writes periodic memory checkpoints (snapshots) of working memory, goal hierarchies, and belief indices to disk.
- In the event of a crash, the system bootstraps from the latest verified snapshot.

#### 2. Graceful Degraded Execution (Failover)
- If premium API endpoints are unreachable, the system automatically redirects planning queries to local fallback models (e.g. quantised edge LLM), downgrading search depth to match local resources.
- If the vector index database becomes corrupted, the retriever temporarily falls back to direct graph-walk and keyword searches while rebuilding the index in the background.

#### 3. Task Recovery
- Suspended goals are re-scheduled during bootstrap restoration, checking state conditions to determine whether to resume execution or trigger compensating rollbacks.
