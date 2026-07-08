# K21-29: Program Integration Matrix

This matrix formalizes the interface dependencies and integration points between K21 and Programs A through T.

---

## 1. Provided & Required Interfaces

| Associated Program | Integration Target | Provided API (by K21) | Required API (for K21) |
| :--- | :--- | :--- | :--- |
| **Program A: Cognitive Core** | Executive CEO | `get_entity()`, `propose_merge()` | Event notifications routing |
| **Program B: Memory Systems** | Memory Consolidator | Candidate facts promotions | `MEMORY_BUS.write()` access |
| **Program D: Learning** | Learning Loop | Prediction error callbacks | Parameter update metrics |
| **Program E: Reasoning** | Reasoning Engines | Active world state snapshot | Graph traversal utilities |
| **Program F: Planning** | Planner | Simulated state forecasting | Planned action schemas |
| **Program J: Safety & Alignment** | Conflict Resolver | Pre-condition constraint check | Wisdom Principle queries |
| **Program N: Scientific Discovery**| Scientist Agent | Causal law accuracy scores | Hypothesis templates |

---

## 2. Integration Pipeline Layout

```
                  Executive Planner (Program F)
                                │ (simulates plan actions)
                                ▼
WorldModelCoordinator <──> PredictiveEngine <──> CausalEngine
                      (Program C / K21)         (Program E)
```
- All requests are routed through the `CognitiveKernel` bus layers, keeping components decoupled.
