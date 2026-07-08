# ADR-22: Neural Integration Layer Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Running neural components (like Large Language Models and vector models) as isolated blocks leads to loose coupling, where the planner cannot constrain LLM generation, or where LLM completions mutate memory states without passing through safety or belief checks.

### Decision
Define a formal **Neural Integration Layer** that establishes the pipeline boundaries through which neural and symbolic systems cooperate.

---

### Pipeline Flow Architecture

```
User Input ──> Perception ──> Embedding Model ──> Hybrid Retriever
                                                       │
                                                       ▼
Act/Output <── LLM Generation <── Planner/Reasoner <── Working Memory
  │
  ▼
Memory Update (TMS) ──> Reflection (Replay)
```

1. **Perception & Embedding**: User inputs or environment signals are standard-encoded and vector-embedded.
2. **Hybrid Retriever**: Searches Differentiable Memory to populate the working memory stack.
3. **Working Memory & Reasoner**: The symbolic reasoning engine (TMS) verifies facts, checking constraints.
4. **Planner**: Decides the next step (POMDP / MCTS).
5. **LLM Generation Gate**: The LLM is used to format output strings or extract tool parameters, but *never* decides the core planning strategy. The LLM functions strictly as a parser, semantic translation bridge, and output text generator.
6. **Memory Update**: LLM outputs or tool results are written as temporary observations to the `WorldModelCoordinator` and must pass through the Bayesian Belief revision before updating long-term memory.
