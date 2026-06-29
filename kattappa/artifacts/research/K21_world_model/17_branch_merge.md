# K21-17: Branch Merge & Promotion Policy

This document formalizes the validation and integration sequence when promoting simulation branch results to the Main World.

---

## 1. The Candidate Event Promotion Flow

Simulation deltas are *never* written directly to Main World beliefs. Instead, they must pass through the validation pipeline:

```
[Simulation Delta] ──> [Generate Candidate Event] ──> [Verification Gate] ──> [Bayesian Update] ──> [Main World]
```

1. **Generate Candidate Event**: The simulation deltas are converted into proposed changes represented as structured events.
2. **Verification Gate**: The `ConflictResolver` and `SelfModel` evaluate verification preconditions (e.g. "Does the proposed file exist on disk?").
3. **Bayesian Update**: If verified, the event is executed, updating the Main World state and revising belief confidence using the Bayesian Engine.

---

## 2. Merge Conflict Resolution Rules

When concurrent branches modify the same entity property:
- **Rule 1: Timestamp Dominance**: The branch containing the more recent observation timestamp is evaluated first.
- **Rule 2: Confidence Weighting**: If timestamps match, the transition outcome with the highest confidence ($C$) dominates.
- **Rule 3: Gated Contradiction**: If deltas are directly opposing (e.g. `online=True` vs. `online=False`) with similar confidence ratings ($\Delta C \le 0.10$), the coordinator raises a contradiction alert, halts the merge, and schedules a verification action.
