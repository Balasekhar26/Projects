# K21-31: Storage Engine Specification

This document details the persistence layouts, SQLite storage formats, index structures, and serialization schemas for the World Model.

---

## 1. SQLite Storage Schemas

To isolate domains, every world instance owns a SQLite database containing the following physical tables:

```sql
-- 1. Entities table
CREATE TABLE IF NOT EXISTS wm_entities (
    uuid TEXT PRIMARY KEY,
    canonical_id TEXT NOT NULL UNIQUE,
    entity_type TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    last_observed REAL NOT NULL,
    causal_rules_json TEXT DEFAULT '[]'
);

-- 2. Properties table (Entity-Attribute-Value schema)
CREATE TABLE IF NOT EXISTS wm_properties (
    entity_uuid TEXT NOT NULL REFERENCES wm_entities(uuid) ON DELETE CASCADE,
    attribute_name TEXT NOT NULL,
    attribute_value TEXT NOT NULL, -- Serialized JSON
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    variance REAL DEFAULT 0.0,
    source TEXT NOT NULL,
    last_updated REAL NOT NULL,
    PRIMARY KEY (entity_uuid, attribute_name)
);

-- 3. Relationships table
CREATE TABLE IF NOT EXISTS wm_relations (
    relation_id TEXT PRIMARY KEY,
    source_uuid TEXT NOT NULL REFERENCES wm_entities(uuid) ON DELETE CASCADE,
    target_uuid TEXT NOT NULL REFERENCES wm_entities(uuid) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    valid_from REAL NOT NULL,
    valid_until REAL
);
```

---

## 2. Index Structures & Serialization

To guarantee sub-millisecond retrieval times:
- **Indices**:
  - `CREATE INDEX IF NOT EXISTS idx_properties_entity ON wm_properties(entity_uuid);`
  - `CREATE INDEX IF NOT EXISTS idx_relations_source ON wm_relations(source_uuid);`
- **Serialization**: Properties value payloads are serialized into compact JSON strings using standardized encoders. Numeric properties preserve their native float precision to prevent rounding errors.
