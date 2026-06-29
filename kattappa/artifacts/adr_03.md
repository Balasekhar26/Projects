# ADR-03: Memory Architecture Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Kattappa needs a unified, high-performance representation of memory that bridges vector searches and symbolic graphs. Operating with separate representations for beliefs, events, documents, and entities creates translation layers and limits the applicability of general cognitive reasoning algorithms.

### Decision
Define a single, canonical `MemoryObject` that is utilized natively by the memory bus, belief engine, planners, and vector indexers:

```python
class MemoryObject:
    # 1. Identity & Git-style Revisions
    memory_id: str          # Immutable global identifier (shared across all revisions)
    revision_id: str        # UUID for this specific state revision
    parent_revision: str    # Reference to parent revision (enabling branching histories)
    
    # 2. System Taxonomy
    # Must be: 'semantic', 'episodic', 'procedural', 'working', 'simulation'
    system_type: str        
    
    # 3. Content
    symbolic_data: Dict[str, Any]
    embedding: Optional[List[float]]
    
    # 4. Belief vs Truth Separation
    belief_probability: float  # Confidence probability [0.0, 1.0]
    truth_status: str          # UNKNOWN, HYPOTHESIS, SUPPORTED, VERIFIED, REFUTED
    
    # 5. Provenance Graph
    provenance_source: str
    derived_from_revisions: List[str]  # links to contributing parent MemoryObjects
    
    # 6. Temporal Interval
    timestamp: float
    validity_interval: Tuple[float, Optional[float]]  # (valid_from, valid_until)
    
    # 7. Act-R Styled Activation Dynamics
    importance: float       # Base importance weight [0.0, 1.0]
    attention_score: float  # Current focus priority
    activation: float       # Dynamic cognitive recall score
    last_activated: float   # Timestamp of last access
    activation_decay: float # Forgetting rate coefficient
    access_count: int
    
    # 8. Enterprise & Metadata Metadata
    schema_version: str
    checksum: str
    embedding_model: str
    symbolic_hash: str
    compression_level: int
    encryption_state: str
    privacy_level: str      # PUBLIC, PRIVATE, RESTRICTED
    owner: str
    ttl: Optional[float]
    archive_state: str      # ACTIVE, ARCHIVED, COLD
    
    relations: List[Relation]
    tags: List[str]
    metadata: Dict[str, Any]
```

---

### Working Memory Subsystem Specification
Working Memory is isolated from Long-term Memory to prevent overloading reasoning engines:
- **Capacity**: Constrained dynamically (e.g. max 7 active nodes/concepts).
- **Focus Stack**: Tracks the current focus of attention using dynamic weighting.
- **Goal Stack**: Tracks active subgoals currently under execution by the planner.
- **Eviction Policy**: Least-Recently-Used (LRU) blended with Act-R activation values.
- **Scratchpad**: Sandboxed area for temporary hypothetical testing.

---

### Memory Dynamics Specifications

#### 1. Retrieval Scoring Function
The retrieval engine scores and ranks candidates using a hybrid mathematical model:
$$\text{Score} = w_1 \cdot \text{VectorSimilarity} + w_2 \cdot \text{GraphConnectivity} + w_3 \cdot \text{BeliefProbability} + w_4 \cdot \text{Activation} + w_5 \cdot \text{TemporalRecency} + w_6 \cdot \text{GoalRelevance}$$
Where:
- $\text{Activation}$ follows Act-R cognitive activation equations:
  $$A_i = B_i + \sum_j W_j S_{ji}$$
- $\text{TemporalRecency}$ decay: $e^{-\lambda \cdot (t - \text{timestamp})}$.

#### 2. Consolidation & Replay Policy
- **Consolidation**: During reflection cycles, high-frequency `episodic` memories are generalized into permanent `semantic` structures. Redundant or duplicated experiences are compressed to prevent memory bloating.
- **Forgetting Policy**: Activation decays exponentially over time relative to its access history. Memory objects with activation dropping below a dynamic threshold are pruned from working memory to persistent cold storage.
