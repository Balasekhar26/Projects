# ADR-01: Cognitive Kernel Communication Routing

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-28
*   **Evidence Level**: **E5**

### Context & Problem
As the number of intelligent sub-systems (Planner, Memory, Scientist, Attention, Context Manager) grew, direct references across modules created circular imports and tight $O(N^2)$ coupling, making the codebase fragile and difficult to extend.

### Decision
Implement a central communication hub—the `CognitiveKernel` singleton—exposing dedicated buses:
- `MemoryBus`
- `GoalBus`
- `EventBus`
- `ContextBus`
- `ToolBus`
- `AgentBus`

All components communicate strictly by calling the kernel buses rather than importing other modules directly.

### Alternatives Considered
- **Direct importing**: Rejected due to circular import locks.
- **Message queue broker**: Rejected due to excess memory overhead and complexity.

### Consequences
- Circular imports are eliminated.
- Single, unified interface simplifies debugging.
- Introduces a single point of failure (mitigated by extensive unit tests).

### Risks & Rollback Plan
- *Risk*: Kernel thread lock contention under high load.
- *Rollback*: Revert commits to tags `kattappa-v1.5-architecture-stable`.
