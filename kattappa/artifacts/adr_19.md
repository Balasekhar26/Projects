# ADR-19: Emotion, Motivation & Value System Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Static planners execute goal trees mechanically, failing to adapt search parameters to time-sensitive constraints or resource deficits. The system needs dynamic, high-level control variables to regulate exploration rates, planning depths, and risk envelopes without complex hardcoding.

### Decision
Define a set of computational **Motivation & Value** control variables that dynamically modulate attention priority, planner heuristics, and memory retrievals.

---

### Core Control Variables (Cognitive Regulators)

1. **Curiosity / Novelty Seeking**: Regulates exploration rate. High curiosity shifts hybrid retriever attention to low-confidence nodes, prioritizing new information over high-confidence paths.
2. **Risk Tolerance**: Modulates planner selection. Low risk tolerance penalizes paths with uncertain state transitions ($\sigma(s) \ge 0.15$), forcing selection of verified deductive actions.
3. **Goal Urgency**: Adjusts search beam widths. High urgency reduces planning depth and restricts exploration, selecting fast reactive reflexes.
4. **Fatigue**: Increases over time relative to tick execution load. High fatigue raises the priority threshold for starting new plans, triggering transition to the offline `Sleep` stage.
5. **Confidence**: Dynamic ratio of successful plans to prediction errors. Low confidence lowers learning rate parameters to prevent unstable policy shifts.

---

### Modulation Matrix

| State Variable | Influence on Attention | Influence on Planner | Influence on Learning |
| :--- | :--- | :--- | :--- |
| **High Urgency** | Focuses on active goal nodes only | Limits MCTS rollouts, uses Reactive | Defer consolidation updates |
| **High Curiosity** | Increases weights for novel nodes | Prefers information-gathering steps | Increases exploration rate |
| **High Fatigue** | Evicts low-attention nodes faster | Limits planning depth capacity | Triggers Sleep consolidation |
| **Low Confidence** | Increases attention on contradictions | Demands human approval verification | Lowers policy update gradients |
