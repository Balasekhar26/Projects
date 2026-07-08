# ADR-07: Reasoning Architecture Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Cognitive problems vary in their logic demands: diagnosing a hardware issue requires abductive diagnosis, path navigation requires spatial/probabilistic tracking, and safety compliance requires deductive verification. Running a single generic reasoning module leads to slow, inaccurate, or over-constrained execution.

### Decision
Define a modular **Reasoning Registry** that exposes specialized reasoning engines. Planners or executive control modules select the reasoning strategy appropriate for the active task.

---

### Reasoning Engine Classification Specs

| Engine Type | Core Reasoning Function | Execution Pathway |
| :--- | :--- | :--- |
| **Deductive** | Strict logical implication verification | Rule matching & logic validation (TMS rules). |
| **Inductive** | Generates general rules from specific observations | Pattern matching over historic episodic logs. |
| **Abductive** | Generates hypotheses explaining observations | Backwards search (finding cause $C$ for effect $E$). |
| **Probabilistic** | Graph belief confidence calculations | Exact joint path probability solver in the PKG. |
| **Counterfactual** | Evaluating speculative outcomes ("what if...") | Simulation delta branch analysis in coordinator. |
| **Causal** | Causal path and dependency tracing | Direct DAG node-edge causality traversals. |
| **Constraint** | Safety boundary compliance verification | Static limits validation checking on active plans. |

---

### Interface Contract

```python
class ReasoningEngine:
    def reason(self, query: Dict[str, Any], context: WorkingMemory) -> ReasoningResult:
        """Executes reasoning logic returning explanations, confidence, and inferences."""
        pass
```
All engine implementations are registered with the `ReasoningRegistry` and are invoked dynamically.
