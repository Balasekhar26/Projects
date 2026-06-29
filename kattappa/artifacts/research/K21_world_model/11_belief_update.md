# K21-11: Belief Update & Calibration Engine

This document specifies the rules and mathematical models used to update, decay, and calibrate beliefs.

---

## 1. Confidence Decay Function

When an entity is not actively observed, the system's confidence in its state decays over time. We implement an **exponential decay function**:
$$C(t) = C_0 \cdot e^{-\lambda (t - t_0)}$$

- $C_0$: Initial observation confidence.
- $\lambda$: Decay rate parameter, specific to the domain and entity type (e.g. `battery_charge` decays faster than `file_existence`).
- $t - t_0$: Time delta since the last verified observation.

---

## 2. Bayesian Confidence Update

When new observations occur, the belief confidence ($C_{bel}$) is updated using a weighted combination of current belief and new observation confidence ($C_{obs}$):
$$C_{new} = C_{bel} + \alpha \cdot (C_{obs} - C_{bel})$$

- $\alpha \in [0, 1]$: Learning rate / credibility weight of the source.

---

## 3. Contradiction Resolution

If a new observation statement conflicts with a high-confidence belief (e.g. "Server is online" vs. "Server is offline"):
1. **Flag Contradiction**: Link the two beliefs via `contradictions` list.
2. **Degrade Confidence**: Temporarily scale down both confidence levels to $C = C \cdot 0.5$.
3. **Trigger Verification**: Schedule a diagnostic action (via the `GoalBus` / Tool Executor) to verify the actual state.
4. **Resolution**: The outcome of the verification action gets observation source weight $\alpha = 1.0$, overriding the refuted belief.

---

## 4. Expected Calibration Error (ECE)

To ensure confidence represents actual accuracy, the system tracks ECE over bins ($B_m$):
$$\text{ECE} = \sum_{m=1}^M \frac{|B_m|}{N} \left| \text{acc}(B_m) - \text{conf}(B_m) \right|$$
- Target: $\text{ECE} < 5\%$.
