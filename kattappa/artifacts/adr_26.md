# ADR-26: Memory Consolidation Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
As Kattappa records daily experiences, the volume of raw logs slows down search queries, degrades vector similarity clustering, and leads to conflicting semantic entries. Ephemeral episodes must be systematically consolidated, deduplicated, and archived.

### Decision
Define a robust **Memory Consolidation** pipeline that organizes long-term storage, indexes semantic properties, and executes forgetting policies.

---

### Consolidation Steps & Rules

#### 1. Semantic Extraction & Graph Optimization
- Processes recent episodic records, extracts entity relationships, and registers them as formal `Relation` links in the Probabilistic Knowledge Graph.
- Merges duplicate relation paths, updating weights and confidences.

#### 2. Vector Indexing & Embedding Refresh
- Periodically clusters embeddings to identify new latent concept groupings.
- If the embedding model version is updated, triggers background re-embedding pipelines to keep the vector database aligned.

#### 3. Deduplication & Summarization
- Compresses redundant episodic traces into high-level summaries.
- Archives low-activation, historic episodes to long-term cold files to optimize working memory footprint.

#### 4. Forgetting Policy
- Applies exponential decay filters:
  $$\text{Activation}_{\text{new}} = \text{Activation}_{\text{prior}} \cdot e^{-\lambda t}$$
- If a memory object has not been accessed for a long period ($ttl$ expires or activation drops below $0.10$), it is migrated from the active database to the `COLD` archive.
