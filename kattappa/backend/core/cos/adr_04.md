# ADR-04: Cognitive Execution Engine Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Kattappa contains several decoupled modules (retrieval, planning, learning, and belief engines). Without a single execution model and scheduling framework, these modules would operate as ad-hoc scripts, creating priority inversions, memory leaks, and speculative failure states.

### Decision
Define a unified **Cognitive Cycle** scheduler that operates as the heartbeat of the Cognitive Operating System:

```
Perceive ──> Normalize ──> Encode ──> Retrieve ──> Reason
                                                     │
                                                     ▼
Repeat <── Sleep <── Replay <── Learn <── Observe <── Plan <── Predict
```

---

### Core Loop Lifecycle Stages

1. **Perceive**: Collect raw events from the external sensors or user input buses.
2. **Normalize & Encode**: Standardize events into canonical types and compute dense vector embeddings.
3. **Retrieve**: Query differential episodic and semantic memory to populate current working memory.
4. **Reason**: Feed working memory into the Belief Engine and execute TMS constraint checks.
5. **Predict & Plan**: Simulate potential futures using the World Model and execute POMDP or heuristic path tree search.
6. **Observe & Evaluate**: Execute actions, compare results to predictions, and calculate the prediction error:
   $$\text{Prediction Error} = \text{ObservedResult} - \text{PredictedOutcome}$$
7. **Learn & Consolidate**: Apply gradients/feedback to planners, beliefs, and embeddings.
8. **Replay & Sleep**: Periodically trigger offline reflections to compress redundancy and reorganize memory clusters.

---

### Operating System Scheduling & Constraints

#### 1. Prioritization & Interrupts
- The cycle runs on a configurable tick duration (e.g. 50ms - 500ms).
- High-priority interrupts (e.g. system resource exhaustion or direct user commands) bypass the current stage and force immediate transition to the `Act` stage.

#### 2. Asynchronous Execution
- **Background Worker threads**: Processes like embedding generation, graph clustering, and episodic memory consolidation are scheduled asynchronously during the `Sleep` stage or when system load is low.
- **Resource watchdogs**: Active task plans are terminated if memory usage or token costs exceed safety thresholds.

#### 3. Speculative Recovery
- Planners execute in temporary delta branches created by the `WorldModelCoordinator`.
- If a path fails verification or exceeds error bounds, the coordinator triggers a rollback, discarding speculative branch updates without mutating Main World beliefs.
