# Kattappa Architecture Decision Log

This log registers the core architectural and design decisions completed across Kattappa's timeline.

---

| Decision ID | Date | Scope | Title | Description / Resolution |
| :--- | :--- | :--- | :--- | :--- |
| **D-K9.5** | 2026-06-28 | Core OS | Cognitive Kernel Integration | Replaced $O(N^2)$ direct component calling with a central routing kernel. |
| **D-K9.6** | 2026-06-28 | Context | Context Manager Compilation | Consolidated goals, failures, and environment into a unified ExecutionContext. |
| **D-K10.5** | 2026-06-28 | Workspace | Transient Executive Registers | Implemented thread-safe active registers mimicking CPU workspace registers. |
| **D-K11.5** | 2026-06-28 | Planner | Priority Conflict Arbitration | Implemented ConflictResolver utilizing hierarchical weighting: Wisdom > Safety Risk > Scientist > Planner. |
| **D-K12.5** | 2026-06-28 | Memory | Significance Consolidation Buffer | Staged raw memory writes inside a SQLite sleep buffer to block low-significance entries from polluting long-term memory. |
| **D-K13.5** | 2026-06-28 | KG | Temporal Graph Range Validation | Added valid_from and valid_until timestamps to nodes and edges. |
| **D-K16.0** | 2026-06-28 | Planner | Predictive Engine Setup | Shifted K16 from raw world modeling to a Predictive Cognition Layer implementing belief state tracking, forward simulation, counterfactual sandboxes, and prediction error decay loops. |
| **D-K20.0** | 2026-06-28 | Core OS | CEO Orchestrator Upgrade | Upgraded ExecutiveAgent into the central Cognitive CEO routing strategies, context managers, and active registers. |
