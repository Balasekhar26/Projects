# K21-28: Mathematical Appendix

This appendix contains the formal mathematical models, notations, and graph equations for the World Model.

---

## 1. Graph Formalism

The World Model state for any world instance is represented as a typed property graph:
$$G = (V, E)$$

- **Vertices ($V$)**: Represent entities:
  $$V = \{ v \mid v = \langle \text{UUID}, \text{CanonicalID}, \text{Type}, \text{Properties} \rangle \}$$
- **Edges ($E$)**: Represent semantic directed relations:
  $$E = \{ e \mid e = \langle v_i, v_j, \text{RelationType}, \text{Confidence}, \text{valid\_from}, \text{valid\_until} \rangle \}$$

---

## 2. Markov Assumptions

The dynamics of state transitions assume the first-order Markov property:
$$P(S_{t+1} \mid S_t, S_{t-1}, \dots, S_0, E_t) = P(S_{t+1} \mid S_t, E_t)$$

For discrete state variables, transitions are modeled via a transition matrix $T$:
$$T_{ij} = P(S_{t+1} = j \mid S_t = i)$$

---

## 3. Bayesian Network Notation

Belief updates are computed over directed acyclic graphs representing causal variables:
$$P(X_1, \dots, X_n) = \prod_{i=1}^n P(X_i \mid \text{Parents}(X_i))$$

---

## 4. State-Space Formulation

The observed state $Y_t$ is a noisy measurement of the true latent believed state $X_t$:
$$X_t = g(X_{t-1}, E_t) + W_t$$
$$Y_t = h(X_t) + V_t$$

- $W_t$: Process noise (modeling prediction uncertainty).
- $V_t$: Measurement noise (modeling observation confidence).
