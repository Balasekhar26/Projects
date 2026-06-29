# K21-21: Architecture Freeze Specification

This document registers the frozen architectural boundaries, structural decisions, and design reviews for Phase K21.

---

## 1. Frozen Architecture Decisions

### Decision A: WorldModelCoordinator Routing
- **Status**: `FROZEN`
- **Specification**: The `WorldModelCoordinator` acts strictly as an API gateway and router. It does not evaluate transitions or execute causal logic directly.

### Decision B: State Branch Promotion
- **Status**: `FROZEN`
- **Specification**: Simulation branches produce *candidate events*, not direct state modifications. Merging a branch propagates delta properties as candidate events to the verification loop.

### Decision C: Entity Inheritance
- **Status**: `FROZEN`
- **Specification**: All entities derive from `Entity` through domain-specific subclasses (`PhysicalEntity`, `DigitalEntity`, `HumanEntity`, `SelfEntity`, `EconomicEntity`, `TemporalEntity`).

---

## 2. Alternatives Analysis

- **Alternative A: Monolithic Database Model**: *Rejected*. Poor thread scaling and lock contentions.
- **Alternative B: Direct Branch Mutation**: *Rejected*. Contaminates real-world historical records; replaced by candidate event pipelines.
- **Alternative C: Coordinator-Level Causality**: *Rejected*. Creates $O(N^2)$ coupling; replaced by decoupled `CausalEngine` routing over the global `EventBus`.
