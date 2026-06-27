# Kattappa Architecture Lock (v1.0)
**Status:** ACTIVE & ENFORCED · **Date:** 2026-06-27  
**Rule:** No new subsystem may be added to Kattappa unless this architecture lock is updated and approved. All code must conform to these specifications.

---

## 1. Folder Structure & Subsystem Boundaries

The codebase is organized into isolated, decoupled subsystems:

```
ult-translator/kattappa/
├── apps/                         # Frontend UIs
│   └── desktop/                  # Tauri + React desktop application
├── backend/                      # Track A: Cognitive AI OS Backend
│   ├── api/                      # Modular FastAPI routers
│   ├── agents/                   # LangGraph agent definitions
│   ├── core/                     # Core cognitive engines (Memory, Planner, SAGE)
│   └── tools/                    # Hardware, browser, voice, and system tools
├── benchmarks/                   # Immutable, versioned evaluation sets
├── configs/                      # Versioned configuration registry files
├── kattappa_data_engine/         # Track B: Data Ingestion & Preprocessing
│   ├── data/                     # Versioned data storage (Corpus v1, v2, etc.)
│   └── pipeline/                 # Processing stages (Ingest, Clean, Dedup, Shard)
├── kattappa_native/              # Track B: PyTorch Foundation Model
│   ├── model/                    # Transformer (RoPE, GQA, KV Cache)
│   ├── training/                 # Trainer, Optimizer, Checkpoint Manager
│   └── evaluation/               # Model benchmark suite
├── kattappa_tokenizer/           # KTP: Independent Tokenizer Program
└── kattappa_runtime/             # Training Runtime & Resource Governor
    └── resource_governor/        # Resource monitor & safety controller
```

### Program Isolation Rules
1. **KTP (Kattappa Tokenizer Program):** Located under `kattappa_tokenizer/`. Completely isolated; versions independently of model training loops.
2. **KGP (Knowledge Graph Program):** Isolated schemas and relation queries. Banned from direct dependencies on vector indices.
3. **`kattappa_runtime/`:** Reserved *only* for the training resource governor, monitor, and sandboxed execution tools. Stubs resembling `backend/core/` are prohibited.

---

## 2. Naming Conventions

* **File and Module Names:** Must use `snake_case` (e.g., `episodic_memory.py`, `action_broker.py`).
* **Class Names:** Must use `PascalCase` (e.g., `KattappaModel`, `MemorySystem`, `PersonalityCouncil`).
* **Method and Function Names:** Must use `snake_case` (e.g., `learn_from_reflection()`, `generate_tokens()`).
* **Constants:** Must use `UPPER_CASE` with underscores (e.g., `MAX_CONTEXT_LEN`, `DEFAULT_BATCH_SIZE`).
* **LangGraph Node Functions:** Must be postfixed with `_node` (e.g., `memory_recall_node`, `council_debate_node`).

---

## 3. Coding Standards & CI/CD Gating

1. **Type Hints:** Mandatory for all function signatures.
2. **Docstrings:** Required for all public classes, methods, and functions.
3. **Import Discipline:** Absolute imports only. No relative imports across root boundaries. No wildcard imports (`import *`).
4. **FastAPI Route Versioning:** All external endpoints must be prefixed with `/api/v1/`. Direct unversioned routing is prohibited.
5. **Supply Chain Security & Dependency Pinning:** All external dependencies must be pinned with exact SHA256 hashes using lockfiles (e.g. `requirements.txt` generated with hash checks). A Software Bill of Materials (SBOM) must be generated for all client releases.
6. **CI/CD Gating Rules:**
   - **Linting:** Code style must pass static analysis before merge.
   - **Unit Tests:** Full test suite run.
   - **Training Smoke Test:** 10 training steps must run without memory spikes or errors.
   - **Regression Gate:** Scorecards must compare PR branch performance against the main branch baseline.

---

## 4. Registry Architecture

To prevent hardcoded settings, all runs must refer to versioned registries:

* **Config Registry (`configs/`):** Contains subfolders: `model/`, `training/`, `dataset/`, `evaluation/`, `inference/`, and `alignment/`. Every experiment log must record the `config_hash` along with the git commit.
* **Benchmark Registry (`benchmarks/`):** Immutable, versioned evaluation sets under `knowledge/`, `reasoning/`, `coding/`, `memory/`, `tool/`, `safety/`, `vision/`, and `multimodal/`.
* **Dataset Registry:** Metadata files (`metadata.json`) per corpus version recording token count, quality score, duplicate removal rates, domain distributions, and raw source licenses.

---

## 5. Interface Freezing & API Contracts

To ensure decoupled growth, contracts between KMP, KOS, and KRI are strictly frozen. The internal module implementations may be modified, but their interfaces must remain stable:

### KOS ↔ KMP Interface (Inference API)
```python
class KMPInferenceInterface:
    def generate(self, prompt: str, max_tokens: int, temperature: float, top_p: float) -> str:
        """Authoritative interface for model generation. Kept stable across model weight/architecture upgrades."""
        pass
```

### KOS ↔ KRI Interface (Evaluation & Registry API)
```python
class KRIEvalInterface:
    def log_experiment(self, experiment_data: dict[str, Any]) -> str:
        """Registers a training run or evaluation run in the KRI registry."""
        pass
    def retrieve_benchmark(self, category: str, version: str) -> list[dict[str, Any]]:
        """Retrieves an immutable benchmark set from KRI."""
        pass
```

---

## 6. Separation of Research and Production Code

Experimental implementations must never directly enter production paths until promoted:
* **Research Paths:** Experimental architectures, temporary scripts, and custom training scripts must reside in designated `research/` directories (e.g., `kattappa_native/research/`).
* **Promotion Gate:** Code can only be moved to production paths after passing unit tests, verification smoke tests, and demonstrating equivalence/improvement on target baseline metrics.

---

## 7. Long-Term Governance

To maintain discipline as the project grows, development must follow these rules:

### Branch Strategy
* `main`: Protected. Holds Stable and LTS releases.
* `develop`: Protected. Integration branch for Developer Preview (DP) builds.
* `feature/*` or `research/*`: Feature and model development branches.

### Review & Approval Requirements
* **Standard PRs:** Requires code review and passing CI/CD checks (linting, units, training smoke tests) before merge to `develop`.
* **Release Approval:** Moving a build from `develop` to `main` (Beta/Stable) requires a completed milestone gate checklist (Gates K0-K15).
* **Architecture Amendments:** Modifying this Architecture Lock requires an approved Request for Comments (RFC) draft.
* **Model Rollback Protocol:** Startup model health checks are mandatory. If a freshly promoted checkpoint fails serving initialization or validation benchmarks, the runtime must automatically roll back to the previously active stable checkpoint.

---

## 8. Secrets & Credentials Security

1. **No Committed Secrets:** Credentials, private keys, cluster pairing tokens, and API tokens must never be written into the codebase or committed to Git.
2. **Standard Loading:** Credentials must be loaded at runtime from environment variables (`.env` files ignored by Git).
3. **Encrypted Fallback:** For distributed cluster pairing and API credentials, production deployments must load keys from a local system keychain or secure encrypted secrets file (e.g. `secrets.enc`).
4. **Local-First Telemetry & Privacy Lock:** Strictly no outbound telemetry phoning home. All monitoring logs and telemetry must remain entirely local. Outbound transmission of performance data is prohibited unless explicitly authorized via a user opt-in prompt.

---

## 9. Disaster Recovery & Weight Backup Policy

1. **Model Checkpoint Replication:** Model checkpoint weights (`.pt` or `.safetensors`) must be automatically replicated to a secondary, external backup volume or encrypted cloud storage bucket upon completing each training epoch.
2. **Registry Mirroring:** The Experiment Registry, Dataset Registry, and configuration folder must be backed up weekly.
3. **Recovery Verification:** The restore process from weights backups must be verified at least once before advancing past milestone K1.

---

## 10. Memory Hierarchy

Kattappa uses a multi-tier memory system. Direct database queries from agents are prohibited; all writes/reads must route through the `MemorySystem` or `MemoryBroker`.

* **SQLite (`warm_memory.db`):** Authoritative, transactional storage for relational data, log histories, and episodic memory indices.
* **ChromaDB:** Vector store for semantic context embeddings and response caching.
* **Working Memory:** Ephemeral session-level context. Must never write directly to SQLite or ChromaDB without routing through the `MemoryBroker` validation gate.
* **ChromaDB Corruption Recovery:** The system must implement automated vector index health-checks at startup. If index corruption is detected in ChromaDB, the system must trigger an automatic index rebuild sourcing from the transactional SQLite episodic memory logs.

---

## 11. Graph Architecture (LangGraph)

* **State Initialization:** All graph nodes must receive and modify the `AgentState` type defined in `backend/core/graph.py`.
* **Node Gating:** Nodes execute only if authorized by `AgentRouter`. Fast path routing intercepts rule-based intents.
* **Safety Isolation:** Dangerous tools (shell commands, system operations) require explicit human-in-the-loop approval.
* **Graceful Degradation fallbacks:** Every node transition in the graph must be protected by local exception catch-blocks. If a cognitive node (e.g., model inference, browser tool, or voice processing) fails due to hardware constraints or timeout errors, the graph must fall back to a safe degradation mode (e.g., Fast-Path RBIL or a text-only mock fallback) without breaking the session.

---

## 12. Plugin SDK

All tools and extensions must implement the Plugin SDK:
* **Manifest (`plugin.json`):** Declares name, entry points, capabilities, and required permissions.
* **Permission Bounds:** Strict gating of file read/write, shell execution, and network access.
* **Supported Plugins:** Browser, Vision, Robotics, Database, Filesystem, Terminal, Voice, Calendar, Email.

---

## 13. Data Pipeline

The dataset engine must process datasets sequentially:
```
  Raw Ingestion ──► Ingestion Metadata ──► Normalization & Cleaning ──►
  Safety Filtering ──► Deduplication ──► Sharding & Bin Packing
```
No raw, undeduplicated, or unvalidated datasets may be fed into `ShardBuilder` or packed by `bin_packer.py`.

---

## 14. Evaluation Philosophy & Model Cards

1. **Comparative Benchmarks:** Every model checkpoint must be evaluated against the previous checkpoint version using `run_eval.py`.
2. **Continuous Regression Testing:** A checkpoint is rejected if its average score across any scorecard category (Knowledge, Reasoning, Coding, Tool Use, Behavior) decreases by >5%, even if reasoning improves.
3. **Model Card Generator:** Every checkpoint save automatically outputs a `MODEL_CARD.md` summarizing architecture, datasets, benchmarks, training time, and safety results.
