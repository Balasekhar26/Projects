# ADR-08: Planning Architecture Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Action selection in varying environments requires different trade-offs: low-latency reflexes require reactive rules, while high-risk structural decisions require rigorous tree exploration (MCTS) or POMDP evaluation. Hardcoding a single planner prevents Kattappa from adjusting to resource limits or latency bounds.

### Decision
Define a modular **Planner Interface** where each planner registers its performance profile. The Meta-Cognition controller selects the planner that matches the resource budget and confidence targets.

---

### Planner Profile Parameters

Each planner must advertise its profile:
- **Cost**: Estimated API/Token and compute costs.
- **Speed**: Expected completion latency (seconds/ticks).
- **Accuracy**: Expected task completion rate.
- **Uncertainty Tolerance**: Stability in partially observable or highly volatile states.

---

### Planner Taxonomy Specifications

| Planner Class | Target Paradigm | Profile Characteristics |
| :--- | :--- | :--- |
| **Reactive** | Stimulus-response reflex rules | Low Cost, Ultra-fast, Low Accuracy, Low Uncertainty tolerance. |
| **Deliberative** | A* search over state spaces | Medium Cost, Medium Latency, High Accuracy, Low Uncertainty tolerance. |
| **Hierarchical (HTN)** | Goal decomposition tree | Medium Cost, Low Latency, High Accuracy, Medium Uncertainty tolerance. |
| **Monte Carlo (MCTS)** | Stochastic rollouts on world models | High Cost, High Latency, Very High Accuracy, High Uncertainty tolerance. |
| **Risk-Aware (POMDP)** | Bellman backup on belief states | High Cost, Very High Latency, High Accuracy, Very High Uncertainty tolerance. |
| **Tool Planner** | Tool use execution chains | Low Cost, Low Latency, Medium Accuracy, Low Uncertainty tolerance. |

---

### Interface Contract

```python
class Planner:
    def get_profile(self) -> PlannerProfile:
        pass
        
    def generate_plan(self, goal: Goal, state: BeliefState, budget: ResourceBudget) -> PlanResult:
        """Generates sequence of actions using the chosen search strategy."""
        pass
```
