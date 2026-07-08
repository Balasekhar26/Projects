# K21: Benchmark Plan

This document outlines evaluation scenarios and metrics used to verify the performance and accuracy of K21.

---

## 1. Scenario-Based Benchmarks

### Scenario A: Object Permanence
- **Procedure**: Add object "file_a" in state "active". Mark object as "deleted". Query the properties of "file_a".
- **Expectation**: Properties remain accessible with a status of "deleted" and confidence reflecting the verification source.

### Scenario B: Multi-step forecasting
- **Procedure**: Propose 3 sequential terminal write actions. Run forward simulation. Run actual actions.
- **Expectation**: Simulated final states match actual outcomes with error delta $\le 10\%$.

### Scenario C: Counterfactual Isolation
- **Procedure**: Run simulation with modification {"battery_level": 10%}. Retrieve battery level from master DB.
- **Expectation**: Master DB returns original level (e.g. 80%); modification exists only inside isolated execution copy.

---

## 2. Evaluation Scoreboards

- **Forecasting Precision**: $P = \frac{\text{Correct Predictions}}{\text{Total Predictions}}$
- **Branch Isolation**: Must verify 100% data partition isolation during concurrent runs.
