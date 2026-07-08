# ADR-32: Resource Manager Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Running neural and symbolic subsystems concurrently consumes extensive hardware resources: host RAM (graph size), GPU VRAM (embeddings/local models), context window tokens, and external API cost budgets. Running without coordination risks process crashes and runaway API charges.

### Decision
Define a runtime **Resource Manager** that coordinates resource limits, schedules background workloads, and enforces hard limits.

---

### Core Specifications

#### 1. Hardware Allocation limits
- **RAM/VRAM Guard**: Limits local memory sizes for active graphs and models.
- **Vector DB Footprint**: Triggers background compression or episodic archival if the vector index size exceeds the active RAM limit.

#### 2. Context Window Gating
- Monitors token usage of LLM perception and planning queries.
- Triggers dynamic memory pruning (summarizing the active working memory) if the input size exceeds $80\%$ of the model's context threshold limit.

#### 3. API Token Budgeting
- Enforces hard daily or monthly financial budgets.
- Halts execution and notifies the user if the cost exceeds safety thresholds.
