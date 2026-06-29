# K21-41: Temporal Reasoning Specification

This document details the temporal representation models, interval algebra, and scheduling constraints within the World Model.

---

## 1. Allen's Interval Algebra

Kattappa uses Allen's Interval Algebra to reason about time-based relationships between events and states:

- **Interval Relations**:
  - $A$ `before` $B$ / $B$ `after` $A$
  - $A$ `meets` $B$ / $B$ `met_by` $A$
  - $A$ `overlaps` $B$ / $B$ `overlapped_by` $A$
  - $A$ `starts` $B$ / $B$ `started_by` $A$
  - $A$ `during` $B$ / $B$ `contains` $A$
  - $A$ `finishes` $B$ / $B$ `finished_by` $A$
  - $A$ `equals` $B$

---

## 2. Future Commitments & Causal Time Windows

To schedule future execution states and evaluate commitments:
- **Causal Time Window**: Defines the valid lifetime of a state transition before a prediction decays to uncertainty:
  $$\text{Validity Window} = [t_{start}, t_{end}]$$
- **Future Commitments List**: An entity-specific ledger registering reserved resources or states:
  ```python
  @dataclass
  class Commitment:
      commitment_id: str
      entity_uuid: str
      allocated_state: dict
      start_time: float
      end_time: float
  ```
- The `Planner` queries commitments before allocating a resource to verify that no collision occurs on the scheduled timeline.
