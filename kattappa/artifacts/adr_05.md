# ADR-05: Evaluation Protocol Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Integrating neural components, learnable embeddings, and probabilistic planners makes system behavior highly non-deterministic. Without a rigorous evaluation protocol, changes could introduce subtle reasoning degradation, retrieval drift, or planning regressions that escape unit tests.

### Decision
Establish a dedicated evaluation framework to benchmark and gate every architectural change. All PR merges must satisfy statistical significance gates.

---

### Benchmark Categories & Acceptance Thresholds

| Subsystem Metric | Target Metric Indicator | Acceptance Threshold |
| :--- | :--- | :--- |
| **Retrieval Recall@K** | Recall for semantic memory nodes | $\ge 0.92$ |
| **Retrieval Latency** | Query latency for hybrid retriever | $\le 45\text{ms}$ |
| **Planning Success Rate** | Goal attainment in simulated environments | $\ge 88\%$ |
| **World Model Accuracy** | Multi-step state prediction accuracy | $\ge 90\%$ |
| **Belief Calibration** | Expected Calibration Error (ECE) | $\le 0.08$ |
| **Tool Selection Accuracy**| F1-score of selected tool signatures | $\ge 0.95$ |

---

### Evaluation Execution Protocols

#### 1. Continuous Integration Gates
- The benchmark suite is executed on every commit to the `develop` or `main` branch.
- Any change that lowers a primary metric below the acceptance threshold is blocked.

#### 2. Regression & Significance Testing
- When a change is proposed to retrieval weights or planner search heuristics, it is compared against the baseline using A/B significance tests.
- **Statistical Significance**: A change is only approved if it demonstrates a statistically significant improvement ($p\text{-value} \le 0.05$ using a paired t-test or Wilcoxon signed-rank test).
- **Ablation Studies**: Subsystems must be ablated to verify that new code additions actually improve performance, rather than just adding parameters.
