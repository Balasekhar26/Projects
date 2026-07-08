# ADR-38: Deployment Architecture Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Kattappa must deploy across multiple environments: locally on developer laptops (Ollama + SQLite), in private clouds (custom Kubernetes clusters + PostgreSQL), and at the edge on resource-constrained devices. Lacking a uniform deployment spec leads to fragmented configurations.

### Decision
Define a unified **Deployment Architecture** supporting Local, Cloud, Edge, and Hybrid deployment profiles.

---

### Core Specifications

#### 1. Deployment Profiles

| Profile | Main LLM Engine | Vector DB Target | Knowledge Graph Storage |
| :--- | :--- | :--- | :--- |
| **Local** | Local Ollama / Llama.cpp | Local ChromaDB / FAISS | Local SQLite / File |
| **Cloud** | Enterprise API Gateway | Managed pgvector | PostgreSQL / Neo4j |
| **Edge** | Small quantized local model | Ephemeral memory cache | Local flat file |

#### 2. Hybrid Mode Configuration
- Hybrid deployments route high-volume, low-security reasoning tasks to local edge instances, while routing complex plans, multi-agent debates, and deep semantic queries to high-capacity cloud endpoints.
- Syncs local episodic slices to remote cloud instances during reflection sleep phases.
