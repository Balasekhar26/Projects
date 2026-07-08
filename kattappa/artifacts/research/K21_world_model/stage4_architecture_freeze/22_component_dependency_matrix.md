# K21-22: Component Dependency Matrix

This document maps public responsibilities, inputs, outputs, and program ownership across World Model components.

---

## Component Matrix

| Component | Responsibility | Inputs | Outputs | Dependencies | Program |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **WorldModelCoordinator** | Routes domain requests, manages branches, and handles versioning. | Domain query, Branch ID, Entity ID | Entity object, Branch ID | `CognitiveKernel` | Program C |
| **CausalEngine** | Matches and executes transition laws across domains. | Observation Event | Secondary Events, deltas | `EventBus` | Program E |
| **BeliefEngine** | Manages probability states, confidence decays, and ECE. | Observation Event, timestamps | Belief state, confidence delta | `Temporal Domain` | Program B |
| **SimulationEngine** | Projects future state transitions over branches. | Action object, branch delta | TransitionResult | `CausalEngine` | Program C |
| **DomainManagers** | Represents entity and property schemas for a domain. | Entity ID | Subclassed Entity | SQLite persistence | Program C |
