# K21-33: Graph Algorithms Specification

This document details the graph traversal algorithms, path resolutions, and alias lookups executed across the World Model.

---

## 1. Graph Traversal Algorithms

Kattappa uses Breadth-First Search (BFS) and Depth-First Search (DFS) queries to resolve relationships and propagate causal properties:

### Causal Path Finding Algorithm (Dijkstra-based)
To find the most reliable causal pathway between two entities $v_{start}$ and $v_{end}$, the engine minimizes the log-confidence cost:
$$\text{Cost}(e) = -\ln(C_e)$$

```python
def find_reliable_path(start_uuid: str, end_uuid: str, max_depth: int = 5) -> List[Relation]:
    # Dijkstra routing minimizing confidence costs
    # Excludes relations where valid_until < current_time
    pass
```

---

## 2. Alias & Canonical Resolution

Alias resolution runs recursively through the alias lookup table before any entity read:
```python
def resolve_canonical_id(identifier: str) -> str:
    # 1. Check if identifier matches UUID format -> return UUID
    if is_uuid(identifier):
        return identifier
        
    # 2. Check Alias registry
    row = db.execute("SELECT canonical_id FROM wm_aliases WHERE alias = ?", (identifier,)).fetchone()
    if row:
        return row["canonical_id"]
        
    # 3. Return identifier as primary canonical ID
    return identifier
```
- Resolution is cached in the `CacheArchitecture` layer to prevent redundant database lookups.
