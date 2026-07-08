# Cognitive Metrics Bible

This document details measurement procedures and mathematical formulas for evaluation across all cognitive dimensions.

---

## 1. Metrics Registry

### 1. Reasoning Calibration Score ($C_{reason}$)
Measures how accurately the system estimates its own confidence:
$$C_{reason} = 1 - \frac{1}{N}\sum_{i=1}^N \left| \text{Confidence}_i - \text{Accuracy}_i \right|$$

### 2. Information Entropy (Uncertainty $U$)
Tracks plan branch entropy based on missing facts and step counts:
$$U = - \sum (P(x) \log_2 P(x))$$

### 3. Prediction Error ($E_{pred}$)
Difference between simulated state expectation ($S_{pred}$) and actual observation ($S_{obs}$):
$$E_{pred} = \| S_{pred} - S_{obs} \|_2$$

---

## 2. Benchmark Methodologies

- **Object Permanence Check**: Simulates file deletions and restores, evaluating whether entity references persist in the World Model.
- **Counterfactual Isolation**: Copies active state, modifies variable X, runs simulation, and verifies zero leakages to the master database.
- **Multistep Forecasting**: Projects state transitions out to 5 steps, comparing results against execution outputs.
