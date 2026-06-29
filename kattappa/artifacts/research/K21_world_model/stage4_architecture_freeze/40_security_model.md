# K21-40: Security Model & Permissions

This document details permissions, cryptographic validation, and execution sandboxing rules for the World Model.

---

## 1. Access Control & Permissions

Sub-agents query the world model through the `WorldModelCoordinator` which gates access based on role permissions:

```
[Agent Query] ──> [Coordinator Security Gate] ──> [Verify Role] ──> [Execute Query]
```

- **Read Access**: Granted to all verified agents.
- **Write Access**: Gated. Only designated agents (e.g. `MemoryKeeperAgent`, `DecisionClassifier`) can commit observation events.
- **Simulation Access**: Granted to `PlannerAgent` inside isolated branch contexts.

---

## 2. Event Payload Cryptographic Signatures

To prevent unauthorized event injection:
- Observation events must be cryptographically signed by the originating tool or agent.
- The `WorldModelCoordinator` validates the signature using public keys before appending events to the `Event Log`.

---

## 3. Sandbox Bounds
- **Resource Constraints**: Counterfactual branches are restricted to a maximum memory footprint of `10MB` and a depth of `10` simulation steps.
- **Lockout**: Any branch violating constraints is terminated immediately by the coordinator, preventing runaway compute consumption.
