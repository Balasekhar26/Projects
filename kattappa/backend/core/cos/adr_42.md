# ADR-42: Data Governance & Lifecycle Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Storing all episodic traces indefinitely violates privacy regulations (e.g. GDPR "right to be forgotten"), risks sensitive data leaks (e.g. API keys captured in task logs), and balloons storage costs.

### Decision
Establish strict **Data Governance & Lifecycle** rules regulating memory retention, data purging, and privacy levels.

---

### Core Specifications

#### 1. Retention & Archival Schedules
- **Episodic Memory Logs**: Purged or summarized after 30 days unless marked `PERMANENT`.
- **Semantic Facts & Ontologies**: Retained indefinitely.
- **Cold Archival Migration**: Long-term files are migrated to encrypted, compressed local files, freeing primary database indexes.

#### 2. Privacy & Redaction Engine
- **GDPR Compliance**: Exposes a `purge_entity(entity_uuid)` endpoint. The system executes a cascading delete, removing the node and all linked relations, and updating embeddings.
- **Sensitive Data Gating**: Automatically scans incoming text, redacting API keys, passwords, and personal identifiers before writing them to long-term memory.
- **Access Ring Gating**: Enforces token-based permissions for agents reading or mutating `RESTRICTED` properties.
