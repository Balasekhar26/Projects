# K21-09: Event Sourced Dynamics Model

This document specifies the pipeline through which the World Model processes changes and updates its internal representations.

---

## 1. The Update Pipeline

Every state update is triggered by an **Observation** and processed event-sourcely:

```
Observation ──> Event ──> Validation ──> State Transition ──> Belief Update ──> Prediction Error ──> Memory
```

1. **Observation**: A sensor reading, tool output, or user input is captured.
2. **Event**: A structured change event (e.g. `file_written`, `cpu_usage_measured`) is published to the `EventBus`.
3. **Validation**: The `ConflictResolver` and `SelfModel` verify constraints and check for anomalies.
4. **State Transition**: The domain model applies transition functions to predict new values.
5. **Belief Update**: Confidence levels and variances are revised using probabilistic rules.
6. **Prediction Error**: Actual outcome is compared with predicted state, adjusting the belief confidence.
7. **Memory**: Significant changes ($\ge 0.50$) are written to `MemoryConsolidator` sleep buffer.

---

## 2. Event Log Structure

Each event is recorded as a structured, versioned, immutable log:
```python
@dataclass
class Event:
    event_id: str
    timestamp: float
    event_type: str        # E.g. 'MODIFY_PROPERTY', 'DELETE_ENTITY'
    target_entity_id: str
    properties_delta: dict
    source: str
    signature: str         # Cryptographic verification sign
```
- Mutating an entity's properties *always* requires producing an Event, ensuring full timeline replay fidelity.
