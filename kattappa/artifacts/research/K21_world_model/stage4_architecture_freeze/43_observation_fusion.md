# K21-43: Observation Fusion Specification

This document details how Kattappa resolves contradictory observations and fuses multi-source inputs into a single believed state.

---

## 1. Conflict Resolution Policy

When observations from different sources disagree (e.g. Tool says `File exists`, User says `File does not exist`):
- **Conflict detection**: Triggered if observations of the same property arrive with opposing values within the same timeline.
- **Resolution Strategy**:
  1. **Weighting by Source Reliability**: Source reliability coefficients ($W_{source}$) are retrieved from the `ToolReliabilityTracker` or User trust registry.
  2. **Freshness Decay**: Observation confidence decays based on its age ($t - t_{observed}$).
  3. **Bayesian consensus**: The believed value $V_{bel}$ is calculated as the probability distribution matching the highest posterior probability:
     $$P(V \mid O_1, O_2) \propto P(O_1 \mid V) P(O_2 \mid V) P(V)$$

---

## 2. Fusion Workflow

```
[Observation 1 (Tool)] ──┐
                         ├──> [Weight & Decay] ──> [Bayesian Consensus] ──> [Updated Belief]
[Observation 2 (User)] ──┘
```
- If the posterior probability difference between two competing values is $\le 0.15$, the coordinator locks the property, flags a contradiction, and issues a verification request.
