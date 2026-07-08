# Kattappa Evaluation Framework

This document defines the capability evaluation methodologies, regression policies, and statistical guidelines for Kattappa.

---

## 1. Capability Metrics

Subsystems are measured across three baseline performance matrices:

| Metric | Dimension | Target | Verification Method |
| :--- | :--- | :--- | :--- |
| **Prediction Accuracy** | World Model / Belief | $\ge 90\%$ | Difference delta on transition predictions vs. reality outcomes. |
| **Plan Feasibility** | Planner | $\ge 95\%$ | Pre-condition and risk evaluations from World Model. |
| **Consolidation Precision** | Memory Consolidator | $\ge 90\%$ | False positive rate of staging promotions to Semantic memory. |
| **Response Pacing** | Attention / Emotion | $\le 1.5\text{s}$ | Average latency under load constraints. |

---

## 2. Regression Gating Policy

Every new iteration or commit must pass through regression gates:
1. **Gate 1: Unit Tests**: 100% test passing requirement.
2. **Gate 2: Integration Verification**: Evaluation of cross-bus communication loops.
3. **Gate 3: Performance Check**: Execution speed, peak RAM, and db connection leaks checks.

If any regression is detected:
- **Immediate Abort**: System rollback to the previous tagged stable release.
- **Fail Logs**: Auto-dump error stack trace and context registers to `backend/data/failures/`.

---

## 3. Statistical Evaluation Rules

To verify learning stability and prevent catastrophic forgetting:
- **Significance (p-value)**: All benchmark metrics improvements must satisfy $p < 0.05$ over baseline comparisons.
- **Sample Count**: A minimum of 30 distinct simulation runs are required to compute metrics confidence intervals.
