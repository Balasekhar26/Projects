# K21-10: Branching Simulator Specification

This document details how Kattappa's World Model simulates alternative futures and replays historical sequences.

---

## 1. Branching Tree Model

Simulations occur on isolated branches descending from the `Main World` state. Branches are hierarchical, allowing nested simulation trees:

```
Main World State (Real Time)
  ├── Branch A (Simulation: Plan Route 1)
  │     └── Branch A.1 (Counterfactual: Tool fails)
  └── Branch B (Simulation: Plan Route 2)
```

---

## 2. Delta-Based Inheritance & Lazy Copy

To prevent copying large databases or property graphs when creating a branch:
- **Parent Reference**: A branch holds a read-only reference to its parent branch (or the main world state).
- **Delta Ledger**: Property reads first check the branch's local delta log (`dict[entity_id, properties_delta]`). If not found, the query propagates recursively up the parent tree.
- **Isolation**: Modifications on a branch are written *only* to the branch's local delta ledger, ensuring 100% isolation with zero write pollution to the parent or Main World.

---

## 3. Temporal Replay & Rollbacks

Replaying historical sequences utilizes the Event Log:
- **Snapshot + Delta Replay**: The simulator loads a database snapshot from a checkpoint timestamp, then sequentially executes events from the `Event Log` up to the target replay timestamp.
- **Rollback**: To rollback, the engine applies inverse event deltas in reverse chronological order, recovering 100% of previous states.
