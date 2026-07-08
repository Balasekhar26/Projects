# K21-13: Formal Mathematics Specification

This document formalizes the mathematical models and equations governing state transitions, belief updates, uncertainty propagation, and calibration within the world model.

---

## 1. State Transition Functions

Given a domain state $S_t \in \mathcal{S}$ and an event $E \in \mathcal{E}$, the transition function $f$ models the next state:
$$S_{t+1} = f(S_t, E)$$

When actions are probabilistic, the transition is represented as a conditional probability distribution:
$$P(S_{t+1} \mid S_t, E)$$

---

## 2. Bayesian Confidence Update

When a new observation $O$ occurs with confidence $C_{obs}$ and source credibility $\alpha \in [0, 1]$, the believed confidence $C_{bel}$ is updated recursively:
$$C_{bel}^{(t+1)} = C_{bel}^{(t)} + \alpha \cdot (C_{obs} - C_{bel}^{(t)})$$

If multiple independent observations $O_1, O_2, \dots$ verify a state, we use the odds-ratio Bayesian aggregation:
$$\text{Odds}(S) = \text{Odds}(S_0) \prod_{i=1}^n \frac{P(O_i \mid S)}{P(O_i \mid \neg S)}$$
$$\text{Confidence}(S) = \frac{\text{Odds}(S)}{1 + \text{Odds}(S)}$$

---

## 3. Entropy & Uncertainty Propagation

Uncertainty $U$ propagates over simulation depth $d$ according to information entropy and transition reliability:
$$U(d) = U_0 + \gamma \log_2(d + 1) + \sum_{k=1}^d H(S_{k} \mid S_{k-1}, E_k)$$

- $U_0$: Initial uncertainty.
- $\gamma$: Domain entropy growth parameter.
- $H(S_{k} \mid S_{k-1}, E_k)$: Transition entropy of step $k$.

---

## 4. Expected Calibration Error (ECE)

Calibration error measures the alignment of estimated confidence with actual accuracy over bins $B_m$:
$$\text{ECE} = \sum_{m=1}^M \frac{|B_m|}{N} \left| \text{acc}(B_m) - \text{conf}(B_m) \right|$$
- Target constraint: $\text{ECE} < 0.05$.
