# ADR-28: Planning Engine Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Different tasks require different searching algorithms: breaking down a massive project requires Hierarchical Task Network (HTN) decomposition, whereas routing tools with uncertain outputs requires MCTS or POMDP logic. Hardcoding a single planning engine limits efficiency.

### Decision
Define a unified **Planning Engine** supporting goal decomposition, HTN execution, MCTS rollouts, and task DAG generation.

---

### Core Specifications

#### 1. Goal Decomposition & HTN
- Recursively decomposes high-level Goals into sub-goals and primitive Actions.
- Builds execution DAGs where nodes are Tasks and edges represent dependencies.

#### 2. Search Algorithms
- **A* / Dijkstra**: Path routing and node connections in the PKG.
- **Monte Carlo Tree Search (MCTS)**: Evaluates prospective action paths on the World Model transition distribution.
- **POMDP Engine**: Manages action values over probability distributions of states (Belief States) under partial observability.

#### 3. Resource & Constraint Gating
- Incorporates cost and latency boundaries directly into the path utility heuristic:
  $$\text{Utility} = \text{ExpectedReward} - \lambda_1 \cdot \text{Cost} - \lambda_2 \cdot \text{Latency}$$
