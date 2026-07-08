# K21-45: Planning Contract

This document formalizes the interface boundaries through which the Planner interacts with the World Model.

---

## 1. Planner Interface API

The `Planner` does not access domain tables directly. It interacts strictly through this contract:

```python
class WorldPlanningInterface(ABC):

    @abstractmethod
    def evaluate_candidate_plan(
        self,
        initial_branch_id: str,
        actions_list: List[Action]
    ) -> Tuple[List[TransitionResult], float]:
        """Runs sequential simulation steps and returns TransitionResults with a composite feasibility score."""
        pass

    @abstractmethod
    def execute_and_verify(
        self,
        action: Action
    ) -> Tuple[bool, float]:
        """Triggers actual action execution, validates outcomes, and logs prediction errors."""
        pass
```

---

## 2. Invariants & Commit Boundaries

- **Isolation Invariant**: Calling `evaluate_candidate_plan` must never modify the Main World database, or alter property configurations on parent branches.
- **Rollback Guarantee**: In case of execution failure during `execute_and_verify`, the system automatically reverts the transaction log to the state of the initial branch checkpoint.
