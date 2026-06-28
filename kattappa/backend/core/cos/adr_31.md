# ADR-31: Evaluation Framework Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Continuous integration of neural and symbolic logic makes behavioral validation difficult. We need automated, granular self-testing measuring not only task success rates but also intermediate reasoning accuracy, latent factuality, memory precision, latency, and token consumption.

### Decision
Define a comprehensive **Evaluation Framework** that operates as an automated testing and calibration pipeline.

---

### Core Specifications

#### 1. Benchmark Suites & Metrics
- **Factuality & Hallucination**: Computes ECE (Expected Calibration Error) and fact verification checks (e.g. cross-referencing generated claims with the semantic graph).
- **Reasoning Quality**: Measures step-by-step logic path accuracy against gold-standard target DAGs.
- **Latency & Token Budget Tracking**: Monitored per tick, verifying that no module violates execution limits.

#### 2. Regression Gating
- Integrates with the CI pipeline.
- Performs statistical significance verification ($p \le 0.05$). If a change to the hybrid retriever or planning heuristics decreases performance on the benchmark suite, it is automatically rejected.
