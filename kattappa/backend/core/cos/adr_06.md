# ADR-06: Knowledge Representation Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
If every cognitive subsystem (planning, retrieval, belief engine) invents its own representation for nodes (entities vs goals vs concepts), the system will face structural drift, duplication, and failure to perform unified cross-domain queries.

### Decision
Define a unified, root-level abstract base interface `KnowledgeNode` from which all semantic nodes in the Probabilistic Knowledge Graph must inherit.

```
                  KnowledgeNode (Abstract Base Class)
       ┌───────────────────┼────────────────────┐
       ▼                   ▼                    ▼
     Entity             Concept               Event
 (Physical, Self)   (Abstract Class)     (Evidence Logs)
       │                   │
       ▼                   ▼
     Goal              Procedure
```

---

### Core Data Structure Specification

```python
class KnowledgeNode:
    """Canonical base class for all semantic representation nodes in Kattappa."""
    node_id: str
    canonical_name: str
    node_type: str            # 'entity', 'concept', 'event', 'goal', 'procedure', 'observation'
    confidence: float         # [0.0, 1.0] uncertainty coefficient
    metadata: Dict[str, Any]
```

#### Derived Subclass Types:
1. **Entity**: Concrete instances (e.g. `PhysicalEntity`, `DigitalEntity`, `SelfEntity`). Represents tangible objects, actors, or systems.
2. **Concept**: Taxonomic groupings or categories (e.g. `Human`, `FelinePredator`). Used for hierarchical ontological reasoning.
3. **Event**: Temporal logs, action transitions, or historical evidence occurrences.
4. **Goal**: Target states representing planned configurations or milestones.
5. **Procedure**: Executable pathways, skills, tool invocation chains, or recipes.
6. **Observation**: Raw sensor readings or inputs, acting as evidence before belief fusion.

---

### Consequences & Rules
- All edges (`Relation`) in the PKG must point between subclass instances of `KnowledgeNode`.
- Ontological transitivity applies across all `Concept` nodes, permitting hierarchical inference.
