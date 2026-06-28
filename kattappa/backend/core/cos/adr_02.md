# ADR-02: Cognitive Learning Substrate (K22.5–K35 Roadmap)

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Up through K22, Kattappa's Cognitive Operating System has been built around symbolic structures (Blackboard, memory buses, belief states, coordinators, probabilistic graphs). However, to scale reasoning towards AGI-grade capabilities, the system must transition from a purely rule-based symbolic engine into a hybrid neural-symbolic platform that learns and generalizes representations continuously.

### Decision
Adopt the following multi-layer roadmap for building the unified learning and decision substrate of Kattappa:

#### Pre-requisites & Foundations (K22.5)
- **K22.5: Evaluation & Benchmark Infrastructure**: Define metrics and benchmarks (Retrieval Recall@K, Expected Calibration Error, planning success rate, world model prediction accuracy) to measure the effectiveness of subsequent phases.

#### Phase 1: Hybrid Neural-Symbolic Foundation (K23–K26.75)
- **K23: Semantic Embedding Layer**: Represent every entity, relation, document, and procedure as dense vector embeddings (1536D / 3072D).
- **K23.5: Differentiable Memory**: Unify symbolic facts and vector embeddings under a single canonical `MemoryObject` container. (See [ADR-03](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/cos/adr_03.md) for specs).
- **K24: Hybrid Retrieval Engine**: Rank memory lookups using a multi-factor scorer fusing Vector Similarity, Graph Connectivity, Belief Confidence, Temporal Recency, and Attention Priority.
- **K25: Representation Learning**: Learn latent concepts by clustering embeddings and automatically proposing new ontological categories.
- **K26: Continual Learning Engine**: Adapt continuously from experience (observations/actions) using memory consolidation techniques to prevent catastrophic forgetting.
- **K26.5: Closed-Loop Decision Feedback**: Implement a prediction error loop ($Result - Prediction$) to continuously update planners, beliefs, and embeddings.
- **K26.75: Meta-Cognition**: Implement cognitive control loops evaluating uncertainty, confidence bounds, and choosing whether to query, plan, act, or ask the user.

#### Phase 2: Decision Intelligence (K27–K30.5)
- **K27: Planner 2.0**: Implement POMDP planning, MCTS, HTN, and information-gathering actions under uncertainty. (See [ADR-08](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/cos/adr_08.md) for specs).
- **K28: Learned World Model Split**:
  - **K28.1: Transition Model**: $P(s' \mid s, a)$ representing state transition distributions.
  - **K28.2: Reward Model**: $R(s, a)$ determining utility payoffs.
  - **K28.3: Uncertainty Model**: $\sigma(s)$ estimating state variance.
  - **K28.4: Counterfactual Generator**: Generates "What-if" branches.
- **K29: Autonomous Scientist**: Expand the scientist into a self-directed loop that formulates hypotheses, executes experiments, and publishes findings back to long-term memory.
- **K30: Multi-Agent Cognitive Society**: Coordinate execution through specialized role-based agents (Planner, Scientist, Engineer, critic, etc.) communicating via workspaces.
- **K30.5: Cognitive Reflection**: Execute offline reflection cycles during idle periods to replay episodes, compress memories, identify contradictions, and refine retrieval parameters.

#### Phase 3: Distributed & Embodied Cognition (K31–K35)
- **K31: Distributed Memory & Knowledge Federation**
- **K32: Multi-modal Perception** (vision, audio, sensors)
- **K33: Embodied Execution** (robotics, IoT, operating systems)
- **K34: Self-Optimization & AutoML**
- **K35: Safe Self-Evolution** (formal verification and evaluation gates)

---

### The Predictive Processing Cycle
To continuously predict incoming observations and adapt, the system loops on:
$$\text{Predict} \rightarrow \text{Perceive} \rightarrow \text{Prediction Error Evaluation} \rightarrow \text{Update World Model} \rightarrow \text{Retrieve} \rightarrow \text{Reason} \rightarrow \text{Plan} \rightarrow \text{Act} \rightarrow \text{Repeat}$$

---

### Suggested Implementation Order
1. **K22.5**: Evaluation framework (See [ADR-05](file:///Users/alwaysdesigns/Documents/Codex/2026-06-23/balasekhar26-ult-translator-https-github-com/work/ult-translator/kattappa/backend/core/cos/adr_05.md))
2. **ADR-03**: Memory architecture specification
3. **K23**: Embedding layer
4. **K23.5**: Differentiable memory
5. **K24**: Hybrid retrieval
6. **K26.75**: Meta-cognition
7. **K26**: Continual learning
8. **K26.5**: Prediction error learning
9. **ADR-04**: Cognitive execution engine specification
10. **K27**: Planner 2.0
11. **K28**: World model split
12. **K29**: Autonomous scientist
13. **K30**: Multi-agent cognition
14. **K30.5**: Cognitive reflection
15. **K31-K35**: Distributed, embodied, and self-improving capabilities

---

### Long-Term Capability Families

| Family | Focus Area |
| :--- | :--- |
| **Foundation** | Memory architectures, ontological representations, vector embeddings, hybrid retrievers. |
| **Cognition** | Specialized reasoning engines, multi-step planners, learned world models. |
| **Learning** | Continual adaptation, memory consolidation replay, meta-learning loops. |
| **Agency** | Multi-agent society, collaboration protocols, executive OS controllers. |
| **Embodiment** | Multimodal perceptual mapping (vision, audio, IoT, actuators). |
| **Governance** | Strict permission gates, safety checks, p-value evaluation policies. |
| **Optimization** | Distributed scaling, auto-tuning, custom hardware acceleration. |

---

### Alternatives Considered
1. **Purely Deep Learning monoliths (Large Language Models)**: Rejected due to lack of explicit auditing, truth maintenance, explainable reasoning traces, and deterministic safety bounds.
2. **Static Symbolic Knowledge Bases**: Rejected due to the inability to dynamically learn new representations, handle unstructured inputs, or scale to complex planning environments.

---

### Consequences
- Unifies deep neural representations and symbolic logic.
- Enables closed-loop learning from prediction error, yielding measurable decision improvements.
- Requires configurable embedding layers and vector indices, which will be integrated as native services.
- The cognitive architecture becomes completely self-correcting and adaptive.

---

### Risks & Rollback Plan

| Risk | Mitigation / Rollback |
| :--- | :--- |
| **Embedding model changes invalidate stored vectors** | Store embedding model version prefix in metadata and support automated background re-embedding pipeline. |
| **Vector DB becomes inconsistent with symbolic memory** | Treat symbolic database as source of truth and rebuild vector index dynamically when discrepancies are detected. |
| **Hybrid retrieval becomes difficult to tune** | Keep retrieval weights configurable and benchmark-driven, optimizing values via reinforcement learning. |
| **Continual learning introduces catastrophic forgetting** | Implement experience replay buffers, structural task isolation, and immutable episodic memory backups. |
| **Planner becomes computationally expensive** | Enforce resource budgeting, beam-width limits, and adaptive search depth policies. |
