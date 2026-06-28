# ADR-33: Multi-Agent Collaboration Protocol Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Coordinating multiple specialized agents (Planner, Scientist, Critic, Engineer) without formal communication rules leads to chaotic interactions, deadlocks, and conflicting memory mutations.

### Decision
Define a robust **Multi-Agent Collaboration Protocol** coordinating communication, consensus voting, arbitration, and delegation.

---

### Core Specifications

#### 1. Debate & Consensus Voting
- When solving complex, high-risk tasks, the Coordinator initiates a **Debate Round**.
- Specialized agents (e.g. Planner proposes a path, Critic reviews it) write structured arguments to a temporary workspace.
- **Consensus**: Action execution requires a majority vote. If consensus is not reached after 3 rounds, the Coordinator arbitrates.

#### 2. Confidence Merging & Conflict Resolution
- When agents assert different beliefs about a state, confidence is merged using weighted noisy-OR:
  $$P(\text{State}) = 1 - \prod_i (1 - w_i P_i)$$
  (where $w_i$ represents the asserting agent's historical reliability).

#### 3. Delegation & Subtasking
- Agents can spawn sub-agents to solve independent subgoals (e.g. Planner delegates code writing to Engineer, and validation to Critic).
- Spawning creates a parent-child context link, blocking parent resolution until the child returns execution outputs.
