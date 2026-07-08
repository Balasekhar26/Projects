# K21-50: Engineering Decision Record & MVP Assumptions

This document registers the core engineering assumptions, prototype limits, and migration plans for the K21 World Model.

---

## 1. Prototype MVP Assumptions vs. Long-Term Targets

To enable rapid prototyping while preserving architectural integrity, Kattappa adopts several simplified MVP configurations:

| Design Dimension | Prototype MVP Decision | Long-Term Target | Migration Plan |
| :--- | :--- | :--- | :--- |
| **Storage Backend** | SQLite (single database file) | Distributed Graph Database (e.g. Neo4j, TinkerPop) | Abstract persistence logic behind the `CognitiveDomain` retrieve/commit APIs. |
| **Property Format** | JSON serialized strings | Structured binary schemas (e.g. Protobuf, Arrow) | Serialization is handled by the `StorageEngine` codec, leaving classes unchanged. |
| **Branch Limit** | Maximum 10 active branches | Dynamic branching, unlimited scale | Implement branch lifecycle garbage collection and delta log eviction. |
| **Scheduler** | FIFO Transaction Queue | Priority-based, pre-emptive scheduler | Upgrade scheduler queues to handle priority tasks first. |

---

## 2. Technical Debt Registry
- **EAV Schema overhead**: The Entity-Attribute-Value schema in SQLite is highly flexible but results in multiple joins during large queries.
  - *Status*: Accepted for prototype.
  - *Risk*: Lower performance under large datasets (mitigated by L2 caching).
