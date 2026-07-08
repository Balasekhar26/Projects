# ADR-17: Episodic Reflection & Sleep Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Running cognitive models continuously generates large volumes of episodic traces. Over time, this leads to memory bloat, high index retrieval latency, and a failure to extract general schemas or learnable heuristics from individual successes or failures.

### Decision
Define a dedicated offline **Episodic Reflection & Sleep** pipeline. When system resource demands are low (e.g. idle ticks), the Executive Controller triggers the sleep state to optimize memory indices and extract generalized procedural skills.

---

### Core Sleep Stages & Operations

#### 1. Memory Replay & Dream Simulation
- **Episodic Replay**: Replays recent successful or failed task paths from episodic memory.
- **Dream Simulation**: Runs speculative variations of the replayed episodes inside the `WorldModelCoordinator` counterfactual sandbox to identify alternative routes, test "what-if" parameters, and reinforce planner policy weights.

#### 2. Experience Compression & Summarization
- Combines redundant episodic steps into structured task summaries.
- Cleans and compresses detail nodes, updating long-term semantic memory and archiving raw episodic data to cold storage.

#### 3. Skill & Knowledge Consolidation
- **Knowledge Abstraction**: Evaluates repeating patterns of entity observations and generalizes them into ontological classes.
- **Skill Extraction**: Extracts highly successful action sequences and saves them as reusable procedural templates in the skill database.

#### 4. Contradiction Discovery & Weight Optimization
- Runs background checks across the entire belief network to identify latent logical contradictions.
- Refines and optimizes associative retrieval weights ($W_j$) and activation decay parameters.
