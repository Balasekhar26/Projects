# K21-16: Simulation Engine Specification

This document details the operation of the Branching Simulator, delta-based state isolation, and simulation pipelines.

---

## 1. Branching & Delta Storage

Simulated states are stored as isolated **Deltas** referenced to a parent branch. A branch contains:
- `branch_id`: UUIDv4
- `parent_branch_id`: Optional[str]
- `deltas`: `Dict[str, Dict[str, Any]]` (Mapping of entity_id $\rightarrow$ property change dict)

### Lazy Entity Retrieval algorithm
```python
def get_property(branch_id: str, entity_id: str, property_name: str) -> Any:
    # 1. Check current branch deltas
    branch = get_branch(branch_id)
    if entity_id in branch.deltas and property_name in branch.deltas[entity_id]:
        return branch.deltas[entity_id][property_name]
    
    # 2. Re-propagate to parent if exists
    if branch.parent_branch_id:
        return get_property(branch.parent_branch_id, entity_id, property_name)
    
    # 3. Fetch from Main World
    return get_main_world_property(entity_id, property_name)
```

---

## 2. Versioned World Snapshots

To support exact reproducibility:
- **Snapshots**: Every transition is saved as a transaction log ID.
- **Rollback / Reset**: Replays start from a base snapshot and execute event sequences sequentially, ensuring 100% state recreation accuracy.
- **Branch Copy**: Creating a counterfactual sandbox branch deep-copies *only* the delta logs tree metadata, achieving $O(1)$ time branch creation.
