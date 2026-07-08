# K21-47: World Model Evaluation Framework

This document formalizes the validation criteria, target thresholds, and regression protocols for the World Model.

---

## 1. Metrics Scoreboard

| Metric | Target | Minimum Threshold | Evaluation Method |
| :--- | :--- | :--- | :--- |
| **Prediction Accuracy** | $\ge 90\%$ | $85\%$ | Difference comparison on simulated vs. actual states. |
| **Calibration Error (ECE)** | $< 5\%$ | $8\%$ | Grouping property confidence bins vs. accuracy rates. |
| **Branch Correctness** | $100\%$ | $100\%$ | Testing branch data leakages across concurrent operations. |
| **Replay Fidelity** | $\ge 95\%$ | $90\%$ | Executing event log histories and verifying final states. |

---

## 2. Regression Protocol

Every update to domain managers or causal engines must run through the target evaluation suite. If any benchmark drops below the minimum threshold:
- The system flags a regression exception.
- State updates are blocked from being merged to the production branch.
- Transaction rollback recovers the database to the latest verified snapshot checkpoint.
