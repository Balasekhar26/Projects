# ADR-45: Release, Versioning & Migration Strategy Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
As code APIs, memory schemas, and database structures are modified, historical data stored in long-term databases can become unreadable. Lacking a migration strategy leads to database corruption, broken retrievals, and loss of valuable learned representations.

### Decision
Adopt a strict versioning and automated schema migration strategy to guarantee backwards compatibility and clean transitions.

---

### Core Specifications

#### 1. Semantic Versioning (SemVer)
- **Major.Minor.Patch**:
  - Major: Breaking API modifications or incompatible memory schema migrations.
  - Minor: Additive, backwards-compatible capabilities or new reasoning engines.
  - Patch: Bug fixes, performance optimizations, or test updates.

#### 2. Schema Migration Pipeline
- Memory database updates must include a corresponding migration script (e.g. Alembic for SQL, custom indices update scripts for vector files).
- Migrations are run automatically on bootstrap.

#### 3. Backward Compatibility Strategy
- If a schema field is deprecated, it is retained as an optional property.
- The `MemoryObject` parser executes dynamic translation mapping old property layouts to the active schema structure.
