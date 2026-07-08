# K21-27: Causal Law Registry Specification (v2)

This document formalizes the classification, metadata tracking, and lifecycle gates for Causal Laws.

---

## 1. Domain Categorization

Causal Laws are categorized under the six cognitive domains:
- **Physical**: Transition laws of physical resources (e.g. battery consumption vs. CPU utilization).
- **Digital**: Executions of files, network packets routing, and API schemas.
- **Human**: Cognitive expectations, emotional triggers, and trust adjustments.
- **Economic**: Compute costs, pricing adjustments, and API consumption parameters.
- **Temporal**: State transitions over elapsed execution ticks.
- **Internal Self**: Resource allocations and sub-agent scheduler loads.

---

## 2. Accuracy & Evaluation Metrics

Causal Laws are treated as living, testable hypotheses carrying validation metrics:
- **Prediction Accuracy ($A_{law}$)**: Percentage of correct forecast transitions:
  $$A_{law} = \frac{\text{Successful predictions}}{\text{Total predictions executed}}$$
- **Evidence Level**: Follows the global E0-E5 hierarchy. Laws default to E0 (Hypothesis) upon registration and must be verified to E3 before production planning integration.

---

## 3. Causal Law Lifecycle States

```
[Registered: E0] ──> [Tested: E2] ──> [Verified: E3] ──> [Production Active: E5]
       │
       └──> [Reputed Failure (Acc < 0.60)] ──> [Deprecated / Retired]
```
- If a law's prediction accuracy drops below `60%`, the `CausalEngine` flags it as deprecated, triggering an alert to the Scientist Agent to regenerate the rule.
