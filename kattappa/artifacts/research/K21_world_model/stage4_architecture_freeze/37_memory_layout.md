# K21-37: Memory Layout Specification

This document details the in-memory (RAM) representation structures of Entity objects and their relation to the database serialization formats.

---

## 1. In-Memory (RAM) Structure

Entities loaded in memory are represented as typed Python dataclasses:

```python
class MemoryEntity:
    """RAM optimized entity model."""
    __slots__ = (
        'uuid', 'canonical_id', 'entity_type', 
        'properties', 'relations', 'confidence', 
        'last_observed', 'causal_rules'
    )
```
- **Optimization (`__slots__`)**: Using `__slots__` reduces Python object memory overhead by up to $70\%$, allowing over 100,000 entities to fit in under `20MB` of RAM.

---

## 2. RAM to Database Mappings

| Field | RAM Type | DB Column Type | Serialization Format |
| :--- | :--- | :--- | :--- |
| `uuid` | `str` | `TEXT` | Native string UUIDv4 |
| `canonical_id` | `str` | `TEXT` | Semantically structured string |
| `properties` | `dict` | `TEXT` (JSON) | UTF-8 JSON payload |
| `relations` | `list` | `TEXT` (JSON) | Foreign keys joined on relation table |
| `causal_rules` | `list` | `TEXT` (JSON) | Array of string Rule IDs |
