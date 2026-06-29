# K21-46: Learning Pipeline Specification

This document details the closed-loop learning pipeline, tracking errors and updating models dynamically.

---

## 1. Learning Loop Architecture

Kattappa operates on a continuous feedback loop:

```
[Inference] ──> [Prediction] ──> [Actual Outcome] ──> [Prediction Error] ──> [Learning Engine] ──> [Model Update]
```

- **Inference**: Active state evaluation ($S_{bel}$).
- **Prediction**: Forward simulated forecast ($S_{pred}$).
- **Prediction Error**: Calculated deviation between $S_{pred}$ and $S_{obs}$:
  $$E_{pred} = |S_{pred} - S_{obs}|$$
- **Learning Engine**: Processes the error to locate incorrect causal rules or stale confidence decay parameters ($\lambda$).
- **Model Update**: Recalibrates parameters and updates SQLite tables.

---

## 2. Invalidation & Tuning

If a causal rule repeatedly generates prediction errors above a threshold (e.g. $E_{pred} \ge 0.50$):
- The rule's confidence score is decayed.
- An alert is sent to the Scientist Agent (Program N) to trigger active learning updates (generating a new candidate rule hypothesis).
