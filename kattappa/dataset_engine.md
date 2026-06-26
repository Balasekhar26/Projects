# Kattappa Data Engine (KDE-v1) — Production Specification & Roadmap

The **Kattappa Data Engine (KDE-v1)** is a highly modular, decoupled, batch-processing pipeline designed to curate premium-grade training datasets for future Kattappa Foundation Models. 

In modern LLM engineering, data curation is the primary differentiator of model capability. The KDE-v1 pipeline ensures that raw sources are transformed into highly structured, clean, deduplicated, and balanced token shards while strictly avoiding common data-poisoning pitfalls.

```
Raw Sources (Books, Web, Docs, Code, Conversations, Notes)
   │
   ▼
[KM-1.0 Ingestion & Fingerprinting] ──> Enforce schema, SHA256 & MinHash, provenance
   │
   ▼
[KM-1.0 Cleaning & Normalization]   ──> UTF-8, Whitespace, Quotes, Boilerplate strip
   │
   ▼
[KM-1.1 Safety & PII Sanitizer]     ──> Redact SSNs, API keys, filter toxic & GPL code
   │
   ▼
[KM-1.3 Bias & Language ID]         ──> Roman Telugu (te-en) code-switch preservation
   │
   ▼
[KM-1.4 Deduplication & AST Dedup]  ──> Global SHA256 & MinHash LSH, AST code dedup
   │
   ▼
[KM-1.4 Contamination Gate]         ──> 13-gram exact, semantic leak check vs eval/benchmarks
   │
   ▼
[KM-1.5 Quality Scoring Engine]     ──> Domain-specific heuristics & metrics
   │
   ▼
[KM-1.6 Filter Validation & Ablation]──> Tiny probe models (10M-50M) check downstream loss
   │
   ▼
[KM-1.0 Tokenization Streamer]     ──> Custom Kattappa BPE, binary array packing
   │
   ▼
[KM-1.0 Shard Builder]              ──> Global shuffle, Train/Val/Test (96%/2%/2%) splits
```

---

## 1. Physical Folder & File Structure

This decoupled structure guarantees complete state isolation, enabling step-by-step reproducibility and deep debugging inspectability across pipeline boundaries.

```
kattappa_data_engine/
├── config/
│   ├── pipeline_config.yaml       # Global thresholds, regex, and hyperparameters
│   └── tokenizer_config.json      # BPE vocab settings and merge files
├── data/
│   ├── raw/                       # Immutable source files
│   │   ├── books/
│   │   ├── web/
│   │   ├── papers/
│   │   ├── code/
│   │   ├── conversations/
│   │   └── docs/
│   ├── cleaned/                   # JSONL: Uniform schema, metadata, and normalized text
│   ├── safe/                      # JSONL: PII redacted, license filtered, safe data
│   ├── deduplicated/              # JSONL: Globally deduplicated documents
│   ├── scored/                    # JSONL: Quality scored and tagged
│   ├── tokenized/                 # Intermediate token arrays (.bin / memory maps)
│   └── shards/                    # Final pre-training output shards
│       ├── train/                 # .bin and .idx shards (96%)
│       ├── validation/            # .bin and .idx shards (2%)
│       └── test/                  # .bin and .idx shards (2%)
├── pipeline/
│   ├── __init__.py
│   ├── ingest/
│   │   ├── base_extractor.py      # Unified schema mapper, SHA256, MinHash generator
│   │   └── lang_detector.py       # Code-switch & Roman Telugu aware language ID
│   ├── cleaning/
│   │   └── text_normalizer.py     # Whitespace, Unicode normalizers, boilerplate strip
│   ├── safety/
│   │   └── safety_filter.py       # PII scrubbing, GPL checker, toxicity filter
│   ├── dedup/
│   │   ├── exact_hash.py          # Fast SHA256 record dedup
│   │   └── minhash_lsh.py         # Locality-Sensitive Hashing near-duplicate indexer
│   ├── scoring/
│   │   └── quality_metrics.py     # Readability scores (prose), compiler/lint tools (code)
│   ├── classification/
│   │   └── domain_tagger.py       # Macro/micro domain router, curriculum tagger
│   ├── tokenizer/
│   │   └── bpe_streamer.py        # Stream pack text into binary arrays using Kattappa BPE
│   └── shard_builder/
│       └── bin_packer.py          # Splits, shuffles, and writes token files (.bin / .idx)
├── src/
│   └── dashboard/                 # Streamlit pipeline monitoring and metric graphs
└── reports/
    ├── quality_reports/           # Quality score distributions & domain cuts
    ├── duplicate_reports/         # MinHash collision logs, repeat distributions
    └── statistics/                # Contamination and final dataset metrics
```

---

## 2. Ingestion Unified Data Schema

Every document output by `pipeline/ingest/` must comply with this rigid, future-proof JSONL schema. It includes metadata placeholders for provenance, fingerprinting, curriculum learning, and future instruction-tuning (SFT/DPO).

```json
{
  "id": "kde_doc_20260625_0019284",
  "source": "github/torvalds/linux/kernel/sched/core.c",
  "content": "/*\n * kernel/sched/core.c\n...\n",
  "language": "en",
  "macro_class": "CODE",
  "micro_class": "C",
  "provenance": {
    "source_id": "gh_linux_core_c",
    "source_url": "https://github.com/torvalds/linux/blob/master/kernel/sched/core.c",
    "license": "GPL-2.0",
    "ingestion_timestamp": "2026-06-25T10:08:00Z",
    "pipeline_version": "v1.0.0"
  },
  "fingerprint": {
    "sha256": "4a8c3d9fb381b827e8201cd6f284e92a839fde1482ba37a1f59265f29d9a1f28",
    "minhash_signature": [1082, 3819, 492, 19284, 8274, 9128, 382, 910]
  },
  "metadata": {
    "char_count": 48210,
    "line_count": 1240,
    "difficulty": 9.5,
    "instruction": "",
    "response": "",
    "conversation": []
  }
}
```

---

## 3. Core Structural Priorities (KMP Hardening)

To protect Kattappa from structural failures, the pipeline enforces strict rules on language, duplication, safety, and validation.

### Priority 1: Roman Telugu & Code-Switch Language Policy (B4)
Standard NLP language detectors (like Google's CLD2, fastText, or `langdetect`) misclassify Roman Telugu (e.g., *“nuvvu ela unnavu, nenu bagunnanu”*) or Telugu-English code-switched text as English, Spanish, Indonesian, or "unknown". This causes native data to be flagged as noise and deleted.
*   **Allowlist Policies**: Explicitly define and preserve `en` (English), `te` (Telugu script), `te-en` (Roman Telugu), and `te-en-hybrid` (Telugu-English code-switch).
*   **Hybrid Detector**: Implement a combined character n-gram + dictionary-lookup heuristic to identify Roman Telugu vocabulary patterns, protecting them from language confidence filters.
*   **Recall Validation**: Measure recall against a hand-curated Telugu/Roman-Telugu test set before shipping any language filter.

### Priority 2: Cross-Split & Multi-Granular Deduplication (D1–D5)
A model trained on test set questions (leakage) gets artificial high scores but fails in production. 
*   **Global-First Dedup**: Deduplication is performed *globally* across the entire dataset before sharding.
*   **Strict Split Isolation**: If documents fall into a MinHash LSH collision cluster (near-duplicates), they must all be assigned to the same shard category (`train` or `validation` or `test`). Near-duplicates must *never* cross the evaluation split.
*   **Code-Aware Deduplication**: Normalize files before hashing (strip docstrings, comments, whitespace, and canonicalize identifiers). This catches forks, duplicate boilerplate, and modified variable copies in source code.
*   **Multi-Granular Substring Dedup**: Implement suffix-array matching to locate exact paragraph-level repetitions within large, otherwise unique documents.
*   **Tail Analysis**: Monitor and report the repetition tail. Cap the maximum copies of any unique document/paragraph (e.g., max 3 copies) to prevent memorization and PII exposure.

### Priority 3: PII, License, & Safety Sanitization (Q4)
*   **PII Scrubbing**: Apply deterministic regex and named entity recognition (NER) models to redact API keys, private ssh-keys, emails, phone numbers, and SSNs.
*   **License Policy Gate**: Identify and quarantine copyleft code licenses (like GPL or AGPL) from the permissive pool to ensure legal safety.
*   **CSAM/Toxicity Scans**: Implement lightweight text matching and toxicity filters to scan and quarantine toxic content, keeping the pre-training database aligned.

### Priority 4: Ablation-Driven Filter Validation (KM-1.6)
Every heuristic filter (readability cutoff, perplexity gate) is a bias decision dressed as an objective threshold. Asserting arbitrary gates (like rejecting all documents with readability score < 60) destroys text diversity and penalizes dense, technical registers.
*   **Ablation Runner**: Every filter must prove its utility. Before shipping a filter:
    1. Compile dataset `Dataset-A` (with filter) and `Dataset-B` (without filter).
    2. Train two small probe models (10M–50M parameters) on both datasets under identical parameters.
    3. Measure perplexity and accuracy on down-stream task evaluations.
*   **Rule**: If a filter does not show a statistically significant reduction in validation loss or an increase in task capabilities, **delete the filter**.

---

## 4. Dataset Distribution & Suitability Targets

### Target Gold-Standard Mix
To produce a well-balanced model capable of logic, coding, narrative reasoning, and dialogue, target the following token mix:

| Domain | Target Ratio | Primary Cognitive Value |
|---|---|---|
| **Books** | 20% | Deep narrative structure, long-term context, complex sentence structures |
| **Code** | 20% | Mathematical, syntactic, and algorithmic reasoning |
| **Technical Docs** | 20% | High-density instruction-following, specifications, API formats |
| **Research Papers** | 15% | Advanced academic vocabulary, rigorous logic, and formal proofs |
| **Conversations** | 15% | Chat formatting, interactive dialogue, multi-turn task solving |
| **Web Pages** | 10% | General knowledge base, fact retrieval, and world awareness |

### Suitability Metrics
*   **Total Tokens & Compression Ratio**: Check output tokens against raw bytes (aim for 3.3 to 3.8 bytes per token).
*   **Vocabulary Coverage**: Ensure the model's vocabulary is active across a broad spectrum, avoiding hyper-concentration in small bands.
*   **Average Sequence Length**: Track average contiguous token lengths to ensure the text isn't fractured into tiny snippets before hitting the `<|endoftext|>` marker.

---

## 5. Revised Kattappa Model Program (KMP) Roadmap

To prevent pre-training failures and data contamination, we expand KM-1 into six structured milestones before jumping to attention-module math:

```
KM-1.0: Kattappa Data Engine
├── Ingestion layer with unified schema
├── Basic text cleaning and BPE tokenization
└── Shard builder (Train/Val/Test bin packing)

KM-1.1: Provenance Engine
├── Traceability tracking (source URLs, hashes, licenses)
└── Data fingerprinting cached during ingest (no re-computation)

KM-1.2: Safety Engine
├── PII identification and scrubbing
├── Permissive vs GPL license filtering
└── Toxicity and CSAM scanning

KM-1.3: Bias Observatory
├── Roman Telugu / Code-Switch custom language ID
└── Domain balance and skew tracking dashboard

KM-1.4: Contamination Engine
├── Benchmark protection (GSM8K, MMLU, HumanEval)
├── Cross-split near-duplicate leak isolation
└── Multi-granular paragraph-level deduplication

KM-1.5: Pre-Flight Evaluation Engine
├── Contamination reports (13-gram overlap & embedding similarities)
└── Length distribution and domain skew analysis

KM-1.6: Filter Validation Engine
└── Automated small-model (10M–50M) ablation running harness
```

---

## 6. Verification & Quality Gates

The KDE pipeline will run an automated test suite verifying:
1.  **Format Integrity**: Every document matches the unified schema and is parseable JSONL.
2.  **Zero Leakage**: No 13-gram overlap or duplicate MinHash exists between the test split and the train split.
3.  **Language Recall**: Telugu/Roman-Telugu text is correctly classified and not deleted.
4.  **No OOMs**: Binary shard building runs within strict RAM boundaries using memory-mapped files.
