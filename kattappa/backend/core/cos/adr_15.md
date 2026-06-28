# ADR-15: Ontology & Knowledge Graph Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Storing entities and relation paths without a structured taxonomic ontology leads to shallow semantics, impossible reasoning connections, name duplication (synonyms referring to the same concept), and schema drift as knowledge evolves.

### Decision
Implement a structured **Ontology & Knowledge Graph** subsystem managing relation taxonomies, inheritance properties, and synonym/identity resolution.

---

### Core Ontological Specifications

#### 1. Relation Taxonomy
Edges in the PKG must follow a validated ontology scheme:
- **Taxonomic / Hierarchical**: `IS_A`, `SUBCLASS_OF`, `PART_OF`.
- **Causal**: `CAUSES`, `PREVENTS`, `TRIGGERS`.
- **Equivalence**: `SAME_AS`, `ALIAS_OF`.

#### 2. Inheritance & Concept Lattice
- Subclasses automatically inherit the properties of their parent classes. For example, if `FelinePredator` has properties `diet=carnivore`, then `Tiger` (where `Tiger SUBCLASS_OF FelinePredator`) inherits `diet=carnivore` unless explicitly overridden.

#### 3. Identity & Synonym Resolution
- **AliasRegistry / Identity Resolution**: Integrates with the `AliasRegistry` to map different names (e.g. "Kishore" and "developer") to a single canonical UUID target.
- **Synonym Merger**: If two nodes are determined to be equivalent (confidence of `SAME_AS` edge $\ge 0.95$), the coordinator triggers an automatic merge of their properties and histories.

#### 4. Versioning & Schema Evolution
- The ontology schema uses semantic versioning. 
- Schema changes are additive. Deprecated properties are preserved with `deprecated=True` in metadata to maintain backwards compatibility with historic memory logs.
