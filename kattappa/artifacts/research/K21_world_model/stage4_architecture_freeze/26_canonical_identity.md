# K21-26: Canonical Identity & Namespaces

This document specifies the identity persistence architecture, semantic naming schemas, and resolution rules.

---

## 1. Identity Dual-Key Schema

Every entity possesses two distinct identifiers:
- **UUID**: Permanent, immutable, random (e.g. `e8b23f0a-10fd-4c6e-8213-39d73d4d3a01`). Used for internal database relations.
- **Canonical ID**: Human-readable, semantically stable, versioned (e.g. `self.cpu.load`). Used for routing and reasoning rules.

---

## 2. Namespace Conventions

Canonical IDs are organized hierarchically:
$$\text{Namespace} = \text{domain} \cdot \text{category} \cdot \text{entity} \cdot \text{attribute}$$

- `self.hardware.cpu.load`
- `digital.filesystem.config_json.exists`
- `human.developer.user_1.trust`

---

## 3. Alias Resolution & Merge Policies

- **Alias Registry Table**:
  - `alias`: str (E.g. `self.processor`)
  - `canonical_id`: str (E.g. `self.hardware.cpu`)
- **Identity Merge**: When two entities are determined to represent the same object:
  1. The primary entity UUID is preserved.
  2. The secondary entity UUID is marked as deprecated and mapped as an alias redirect.
  3. Properties delta histories are merged chronologically into the primary entity log.
