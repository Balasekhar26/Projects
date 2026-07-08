# ADR Proposal: Unified Hierarchical Probabilistic World Model (K21)

*   **Status**: `PROPOSED`
*   **Evidence Level**: **E1** (Based on Active Inference and Object-Centric representation literature)

---

## 1. Context & Problem
Currently, Kattappa's predictive systems operate directly on raw strings and disconnected episodic logs. **K21** transitions the architecture to a **Unified Hierarchical Probabilistic World Model** containing six synchronized domains (Physical, Digital, Human, Internal Self, Temporal, and Economic). Under this architecture, every entity represents a structured object containing properties, constraints, beliefs, and causality mappings, enabling forward simulation, counterfactual sandboxes, and offline temporal replays.

---

## 2. Decision
Implement **Option B: Fully Segmented Cognitive Domains** coordinated by a central `WorldModelCoordinator`. Storage is isolated as an implementation detail. Causal relationships are evaluated separately by a dedicated `CausalEngine` routing secondary events across domains via the global `EventBus`.

---

## 3. Open Research Questions for the Architect

1. **Lazy Branch Merges**: When a simulation branch is merged back to the Main World, should deltas overwrite previous beliefs directly, or trigger a full Bayesian update event cycle on the main timeline?
2. **Decay Parameter Tuning**: Should decay rate lambda ($\lambda$) be configured statically per entity type, or updated dynamically by the learning engine based on historical prediction error metrics?
3. **Observation Verification**: When an observation conflicts with existing high-confidence beliefs, should the coordinator block it automatically, or route it to the Causal Engine to trigger verification actions?
