# K21-38: Distributed Execution & Multi-Agent Synchronization

This document specifies the locking, consensus, and synchronization protocols required when executing across multiple sub-agents and users.

---

## 1. Concurrency Control & Locking

To prevent race conditions during concurrent executions:
- **Read Locks**: Multiple sub-agents can read from the `Main World` (or shared parent branches) concurrently without blocking.
- **Write Locks (Coordinator-level)**: Writing to the `Main World` event log is serialized. If agent $A$ is committing a merge event, coordinator blocks agent $B$'s write commit request until the transaction completes.
- **Distributed Lock manager**: Uses a file-based lock file (`.wm_lock`) or Redis/SQLite advisory locks when running across separate operating system processes.

---

## 2. Multi-Agent Synchronization

```
Agent A ──> Propose delta A ──┐
                              ├──> [Event Validation] ──> [Merge Branch]
Agent B ──> Propose delta B ──┘
```

- **Conflict Detection**: The WorldModelCoordinator checks for overlapping properties deltas in concurrent merge proposals.
- **Arbitration Policy**: If conflict occurs, it falls back to the `ConflictResolver` rules (ADR-01/interfaces.md).
