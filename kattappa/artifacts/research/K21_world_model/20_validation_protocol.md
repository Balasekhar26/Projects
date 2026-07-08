# K21-20: Validation Protocol & Exit Criteria

This document defines the formal validation sequence and exit criteria required for K21 to advance across stages.

---

## 1. Exit Criteria for Prototype Phase (Stage 5)

To advance K21 to the Prototype Phase (Stage 5), the design must satisfy:
- [x] All 20 research documents created and compiled.
- [x] Mathematics of Bayesian updates and ECE calibration formulated.
- [x] API interfaces for WorldModelCoordinator typed.
- [x] Key failure modes and mitigations mapped.

---

## 2. Regression & Validation Gates

During Stage 10 (Verification) and Stage 11 (Integration), the prototype must pass:
1. **Branch Isolation check**: Verify that concurrent branch runs do not leak state modifications to the main timeline.
2. **Replay Fidelity check**: Execute a replay of 50 consecutive historical events, verifying final state matches original with $\ge 95\%$ accuracy.
3. **Causal Propagation check**: Digital actions must successfully generate secondary event warnings across Physical, Self, and Human domains.
4. **Performance Budget limits**:
   - Branch creation: $\le 10\text{ms}$.
   - State transition evaluation: $\le 50\text{ms}$.
   - Peak RAM usage overhead: $\le 50\text{MB}$.
