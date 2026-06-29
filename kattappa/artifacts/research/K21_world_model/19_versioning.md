# K21-19: Versioning & Snapshot Strategy

This document details the versioning rules, schema migration policies, and snapshot mechanisms of the World Model.

---

## 1. Versioning Protocol

Kattappa enforces Semantic Versioning (`MAJOR.MINOR.PATCH`) on:
- **Interfaces**: Public Coordinator APIs (e.g. `v1.0.0`).
- **Causal Laws**: Registered rules templates (e.g. `law_battery_decay_v1.2.0`).
- **World Schemas**: Domain taxonomy subclass maps.

### Interface Modification rules
- **Major upgrades**: Require updating the global `adr_index.md` and adding a transition migration helper.
- **Minor / Patch upgrades**: Must maintain backward compatibility with existing SQLite tables and delta ledgers.

---

## 2. World Snapshot Registry

World states are snapshotted to disk during checkpoint triggers:
- **Snapshot ID**: `snap_{domain}_{timestamp}_{version}`
- **Snapshot Storage**: Flat SQLite files or JSON exports containing entities, properties, and active relationships.
- **Reproducibility**: Experiments declaring a snapshot dependency reload the target state, run simulations, and compare outputs.
