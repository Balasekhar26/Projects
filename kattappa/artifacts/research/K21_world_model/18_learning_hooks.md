# K21-18: Learning Hooks & Calibration Specification

This document details how prediction errors drive continuous model updates and parameter calibrations.

---

## 1. Prediction Error Feedback Loops

Every action outcome observation is compared with the forecasted predicted state to compute the Prediction Error ($E_{pred}$):

```
Actual Observation ──┐
                     ├──> [Compare] ──> [Error Delta] ──> [Decay Confidence] ──> [Tune Causal Rules]
Predicted State ─────┘
```

1. **Error Delta Calculation**: Measures mismatch of state keys or properties.
2. **Confidence Decay**: If $E_{pred} > 0.0$, the parent belief's confidence decays:
   $$C_{new} = C_{old} - (E_{pred} \cdot \beta)$$
3. **Causal Rule Tuning**: If a causal rule repeatedly generates high prediction errors ($E_{pred} \ge 0.50$ over $\ge 5$ runs), the rule's internal confidence parameter is scaled down, triggering a reflection event to regenerate the rule.

---

## 2. Adaptive Decay Lambda Tuning

Confidence decay lambda ($\lambda$) is adapted dynamically based on observation statistics:
$$\lambda_{new} = \lambda_{old} + \eta \cdot (E_{pred} - \bar{E}_{pred})$$

- $\eta$: Learning rate parameter for decay calibration.
- $\bar{E}_{pred}$: Historical average prediction error for this entity type.
- If an entity remains stable with low prediction errors, its decay rate $\lambda$ is decreased (meaning confidence persists longer).
