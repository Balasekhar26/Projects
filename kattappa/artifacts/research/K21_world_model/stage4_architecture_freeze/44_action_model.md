# K21-44: Unified Action Model

This document defines the schema contracts, validation rules, and evaluation metrics for actions executed on the World Model.

---

## 1. Action Schema Contract

Every action proposed by the Planner is represented as a structured object:

```python
@dataclass
class Action:
    action_id: str
    action_type: str        # E.g. 'write_file', 'api_call'
    parameters: dict
    preconditions: dict     # Expected states and properties constraints
    effects: dict           # Expected state transformations
    cost: float             # Compute, token, or time cost
    reward: float           # Goal alignment value
```

---

## 2. Validation & Precondition Checks

Before an action is simulated:
- The `SimulationEngine` queries the current branch state to verify all preconditions are satisfied.
- If a precondition has confidence $C < 0.70$ or is directly violated, the simulator flags the step as **unfeasible** and degrades the plan feasibility score.
- **Effects Evaluation**: The simulator applies the effects to the branch's delta ledger, propagating changes to successor states.
