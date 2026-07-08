# K21-32: Query Engine Specification

This document defines the query syntax, evaluation pipelines, and index optimizations for retrieving objects from the World Model.

---

## 1. Unified Query Interface

The `QueryEngine` provides a declarative syntax for retrieving entities and relationships across domains:

```python
class WorldQuery:
    """Structure for defining entity filters."""
    domain: str
    entity_type: Optional[str] = None
    canonical_pattern: Optional[str] = None  # E.g. 'self.hardware.*'
    properties_filter: Dict[str, Tuple[str, Any]] = field(default_factory=dict) # operator -> val
    min_confidence: float = 0.0
```

---

## 2. Query Execution Pipeline

```
[WorldQuery] ──> [Query Parser] ──> [Query Optimizer] ──> [SQL Generator] ──> [Domain DB]
```

1. **Query Parser**: Translates `WorldQuery` fields and namespace wildcard patterns (e.g. `*.cpu.*`) into structured internal objects.
2. **Query Optimizer**: Checks for cached results and filters index conditions (e.g. index on `entity_type`).
3. **SQL Generator**: Constructs optimized SQL SELECT queries joining `wm_entities` and `wm_properties`.
4. **Execution**: Executes the query and translates rows into domain-specific subclass Entity models.
