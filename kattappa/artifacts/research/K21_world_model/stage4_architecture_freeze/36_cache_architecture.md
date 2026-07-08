# K21-36: Cache Architecture

This document outlines the memory optimization, caching layers, and invalidation strategies within the World Model.

---

## 1. Caching Levels

To reduce SQLite database lookups under high query rates, Kattappa implements a multi-level caching system:

```
[Query API] ──> [Level 1: Thread-Local Cache] ──> [Level 2: Global LRU Cache] ──> [Domain DB]
```

- **Level 1 (L1)**: Transient thread-local cache containing entity lookups for the duration of a single execution tick.
- **Level 2 (L2)**: Least Recently Used (LRU) global cache containing the 1,000 most frequently queried Entities.

---

## 2. Delta Log Caching

When evaluating simulation branches, the delta logs are stored in a dedicated memory cache:
- **Cache Format**: `dict[branch_id, dict[entity_uuid, property_deltas]]`
- **Cache Invalidation**:
  - When a branch is merged, its delta logs are deleted from the memory cache.
  - When a branch is discarded (or a counterfactual sandbox completes), its keys are evicted immediately.

---

## 3. Cache Invalidation Rules

- **Write Invalidation**: Any direct write event committed to the `Main World` immediately invalidates corresponding L2 cache entries.
- **Alias Update**: Adding an alias invalidates the translation cache.
