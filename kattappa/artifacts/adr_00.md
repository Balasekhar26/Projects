# ADR-00: Cognitive Operating System Architecture (Master Specification)

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Kattappa is composed of diverse subsystems (Attention, Memory, Planners, Reasoners, World Model, Truth Maintenance System, Conversation Engine). Without a unified, end-to-end flow mapping these subsystems, the engineering implementation risks fragmentation, duplication, and execution conflicts.

### Decision
Establish a master **Cognitive Operating System Architecture** defining the definitive execution flow from user input to agent action and learning feedback.

---

### End-to-End Execution Flow (The Cognitive Pathway)

```
       [ User Input ]
             │
             ▼
      [ Perception ] (ADR-23: normalizing text, vision, files, speech)
             │
             ▼
   [ Conversation Engine ] (ADR-20: grounding & turning repair)
             │
             ▼
   [ Executive Controller ] (ADR-11: scheduling attention ticks & goals)
             │
             ▼
       [ Attention ] (ADR-18: saliency, recency, surprise interrupts)
             │
             ▼
    [ Hybrid Retriever ] (ADR-24: vector similarity + graph scoring)
             │
             ▼
     [ Working Memory ] (ADR-03: focus stack, goals, scratchpads)
             │
             ▼
    [ Reasoning Registry ] (ADR-07: deductive, causal, abductive logic)
             │
             ▼
     [ Meta-Cognition ] (ADR-25: confidence & stopping criteria)
             │
             ▼
    [ Planner Registry ] (ADR-08: POMDP, MCTS, HTN selection)
             │
             ▼
     [ Action Executor ] (ADR-24: action queues & sandboxes)
             │
             ▼
       [ Observation ] (ADR-02: sensory measurements)
             │
             ▼
 [ Truth Maintenance System ] (ADR-16: belief revisions & Bayesian updates)
             │
             ▼
      [ Memory Update ] (ADR-03: differential long-term writes)
             │
             ▼
   [ World Model Update ] (ADR-14: dynamics & prediction error check)
             │
             ▼
     [ Response/Act ] ──> (Output to User / Environment)
             │
             ▼
     [ Sleep/Replay ] (ADR-17 & ADR-26: summarization & consolidation)
```

---

### Integration Principles
- All memory updates must pass through the **Truth Maintenance System** (ADR-16) to verify logical consistency and calculate Bayesian likelihood posteriors before updating long-term repositories.
- Planners execute actions speculatively inside isolated coordinator branches. The main state is only mutated when the action executes in reality and its observation is verified.
