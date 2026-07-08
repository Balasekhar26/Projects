# ADR-41: Configuration & Feature Flags Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Hardcoding thresholds (e.g. min belief probabilities, decay coefficients, attention weights) prevents flexible runtime tuning. Furthermore, we need the ability to toggle advanced cognitive features (like counterfactual simulations or multi-agent debates) without code redeployment.

### Decision
Define a dynamic **Configuration & Feature Flag Registry** that loads settings from structured JSON/YAML configurations and supports live updates.

---

### Core Specifications

#### 1. Config Profile Registry
- Loads configurations mapping system parameters (e.g. `max_working_memory_nodes`, `attention_decay_rate`).
- Environments (Dev, Staging, Prod) override defaults.

#### 2. Dynamic Feature Flags
- Exposes feature flags controlling active strategies:
  - `enable_mcts_planner`: Toggles Monte Carlo search.
  - `enable_agent_debate`: Toggles agent debate consensus.
  - `strict_tms_resolution`: Forces synchronous rollback on logical contradictions.

#### 3. Real-Time Updates
- Config variables are updated dynamically at runtime without restarting the main executive controller loop, permitting reinforcement learning controllers to tune retrieval weights live.
