# K21: Literature Review & SOTA Comparison

This document reviews scientific literature and compares current state-of-the-art approaches to world modeling in cognitive systems.

---

## 1. Literature Survey

### Active Inference & Free Energy Principle (Friston)
- **Concept**: Cognitive agents act to minimize free energy (the difference between internal expectations and sensory observations).
- **Application**: Grounding prediction errors to adjust belief confidence levels.

### Object-Centric Representations (Locatello et al.)
- **Concept**: Segmenting scenes or environments into discrete object slots containing properties rather than flat representations.
- **Application**: Mapping entities (files, servers, users) to individual database rows containing properties.

### Predictive State Representations (PSRs) (Singh et al.)
- **Concept**: Storing state representations solely in terms of predictions of future test outputs rather than latent variables.
- **Application**: Storing probability forecasts inside the belief schema.

---

## 2. State-of-the-Art Comparison Matrix

| System / Theory | State Representation | Uncertainty Handling | Simulation Strategy | Replay |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-R** | Declarative chunks (flat) | Static activations | Rule production loops | None |
| **SOAR** | Working memory graph | Hardcoded constraints | Sub-goaling | None |
| **MuZero (DeepMind)** | Latent state vector | None | Monte Carlo Tree Search | None |
| **Kattappa K21** | Hierarchical Property Graph | Confidence & Entropy | Forward / Counterfactual / Replay | Temporal rollback |
