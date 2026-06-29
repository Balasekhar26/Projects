# ADR-16: Truth Maintenance System (TMS) Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Cognitive agents continuously receive conflicting, noisy, or retracted evidence. Directly overwriting beliefs leads to logical contradictions, loss of justification traces, and inability to perform non-monotonic reasoning (revising a belief when a supporting assumption is retracted).

### Decision
Define a formal **Truth Maintenance System (TMS)** that coordinates recursive belief revision, contradiction resolution, and Bayesian evidence fusion.

---

### Core Components & Specs

#### 1. Dependency Graph & Justification
- Every `Belief` is registered as a node in a directed dependency graph.
- An edge represents a **Justification** linking support nodes (assumptions, observations, or prior rules) to target beliefs:
  $$\text{Justification}: \{\text{In-List}\} \cup \{\text{Out-List}\} \rightarrow \text{Belief}$$
  - **In-List**: Supporting beliefs that must be active (status `BELIEVED`).
  - **Out-List**: Contradictory beliefs that must be inactive (status `RETRACTED` / `REFUTED`).

#### 2. Non-Monotonic Belief Revision
- When a supporting observation is retracted, the TMS executes recursive propagation:
  - If a belief has no active justifications left, its status changes to `RETRACTED`.
  - All downstream beliefs derived from it are recursively retracted.

#### 3. Contradiction Detection & Resolution
- If two active beliefs contradict (e.g. $A \land \neg A$, or mutually exclusive values for a property), a `Contradiction` object is instantiated.
- **Resolution**: The TMS traces the dependency paths of both contradicting nodes back to their base Assumptions. It discounts or refutes the assumption with the lowest Bayesian likelihood posterior, resolving the conflict.

#### 4. Bayesian Evidence Fusion
- Incoming observations update confidence using likelihood ratios:
  $$\text{Odds}_{\text{new}} = \text{Odds}_{\text{prior}} \times \text{LR}$$
  - If the posterior probability drops below $0.50$, the belief status transitions to `RETRACTED` or `REFUTED`.
