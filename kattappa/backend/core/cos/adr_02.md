# ADR-02: Cognitive Learning Substrate (K22.5–K35 Roadmap)

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Up through K22, Kattappa's Cognitive Operating System has been built around symbolic structures (Blackboard, memory busses, belief states, coordinators, probabilistic graphs). However, to scale reasoning towards AGI-grade capabilities, the system must transition from a purely rule-based symbolic engine into a hybrid neural-symbolic platform that learns and generalizes representations continuously.

### Decision
Adopt the following multi-layer roadmap for building the unified learning and decision substrate of Kattappa:

#### Pre-requisites & Foundations (K22.5)
- **K22.5: Evaluation & Benchmark Infrastructure**: Define metrics and benchmarks (Retrieval Recall@K, Expected Calibration Error, planning success rate, world model prediction accuracy) to measure the effectiveness of subsequent phases.

#### Phase 1: Hybrid Neural-Symbolic Foundation (K23–K26.5)
- **K23: Semantic Embedding Layer**: Represent every entity, relation, document, and procedure as dense vector embeddings (1536D / 3072D).
- **K23.5: Differentiable Memory**: Unify symbolic facts and vector embeddings under a single canonical `MemoryObject` container.
- **K24: Hybrid Retrieval Engine**: Rank memory lookups using a multi-factor scorer fusing Vector Similarity, Graph Connectivity, Belief Confidence, Temporal Recency, and Attention Priority.
- **K25: Representation Learning**: Learn latent concepts by clustering embeddings and automatically proposing new ontological categories.
- **K26: Continual Learning Engine**: Adapt continuously from experience (observations/actions) using memory consolidation techniques to prevent catastrophic forgetting.
- **K26.5: Closed-Loop Decision Feedback**: Implement a prediction error loop ($Result - Prediction$) to continuously update planners, beliefs, and embeddings.

#### Phase 2: Decision Intelligence (K27–K30)
- **K27: Planner 2.0**: Implement POMDP planning, MCTS, HTN, and information-gathering actions under uncertainty.
- **K28: Learned World Model**: Leverage deep neural transition models to predict future state distributions $P(\text{next\_state} \mid \text{action})$ when explicit symbolic rules are unavailable.
- **K29: Autonomous Scientist**: Expand the scientist into a self-directed loop that formulates hypotheses, executes experiments, and publishes findings back to long-term memory.
- **K30: Multi-Agent Cognitive Society**: Coordinate execution through specialized role-based agents (Planner, Scientist, Engineer, critic, etc.) communicating via structured workspaces.

#### Phase 3: Distributed & Embodied Cognition (K31–K35)
- **K31: Distributed Memory & Knowledge Federation**
- **K32: Multi-modal Perception** (vision, audio, sensors)
- **K33: Embodied Execution** (robotics, IoT, operating systems)
- **K34: Self-Optimization & AutoML**
- **K35: Safe Self-Evolution** (formal verification and evaluation gates)

---

### Canonical Memory Object Specification
To support branching hypotheses and activation dynamics without translation layers, all subsystems share this structure:
```python
class MemoryObject:
    # Immutable Identity & Git-like revision history
    memory_id: str
    revision_id: str
    parent_revision: Optional[str]
    
    # Memory System Taxonomy
    # "semantic", "episodic", "procedural", "working", "simulation"
    system_type: str  
    
    # Content & Semantic Fields
    symbolic_data: Dict[str, Any]
    embedding: Optional[List[float]]
    
    # Belief vs Truth separation
    belief_probability: float
    truth_status: str  # UNKNOWN, HYPOTHESIS, SUPPORTED, VERIFIED, REFUTED
    
    # Provenance Graph tracking
    provenance_source: str
    derived_from_revisions: List[str]  # links to parent MemoryObjects
    
    # Temporal metrics
    timestamp: float
    validity_interval: Tuple[float, Optional[float]]
    
    # Act-R styled activation dynamics
    importance: float
    attention_score: float
    activation: float
    last_activated: float
    activation_decay: float
    access_count: int
    
    relations: List[Relation]
    tags: List[str]
    metadata: Dict[str, Any]
```

---

### The Unified Cognitive Cycle
Execution operates continuously on a single repeating loop:
$$\text{Perceive} \rightarrow \text{Retrieve} \rightarrow \text{Reason} \rightarrow \text{Plan} \rightarrow \text{Predict} \rightarrow \text{Act} \rightarrow \text{Observe} \rightarrow \text{Learn} \rightarrow \text{Consolidate} \rightarrow \text{Sleep/Replay} \rightarrow \text{Repeat}$$

---

### Architecture Maturity Model
To track absolute engineering progress independently of feature implementation detail:

| Level | Name | Primary Capability |
| :--- | :--- | :--- |
| **L0** | Symbolic Reasoning | Graph paths, Truth Maintenance, rule logic |
| **L1** | Hybrid Memory | Unification of vector embeddings and facts |
| **L2** | Learned Retrieval | Adaptive multi-factor ranking and scoring |
| **L3** | Continual Learning | Closed-loop prediction error reinforcement |
| **L4** | World Modeling | Probabilistic state distribution forecasting |
| **L5** | Autonomous Planning | POMDP under partial observability |
| **L6** | Scientific Reasoning | Hypothesis generation and autonomous experiments |
| **L7** | Multi-agent Cognition | Role-based agent societies and consensus |
| **L8** | Embodied Cognition | Real-time multi-modal perceptual loops |
| **L9** | Self-Improving OS | Full self-directed code adaptation and auto-tuning |

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
