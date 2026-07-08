# ADR-25: Meta-Cognition Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
If a cognitive agent immediately starts executing a planner without checking whether it has enough information, it risks making premature decisions, selecting incorrect tools, or providing low-confidence answers to the user.

### Decision
Define a distinct **Meta-Cognition** controller acting as the internal executive regulator that monitors confidence, maps uncertainty, and chooses the optimal reasoning and planning strategy.

---

### Core Responsibilities & Rules

#### 1. Confidence & Uncertainty Estimation
- Prior to launching a planner, Meta-Cognition computes the active task's uncertainty bounds $\sigma(s)$.
- If $\sigma(s) \ge 0.40$, it halts the plan generation and triggers an information-gathering sub-action (such as asking the user for clarification or querying long-term research indices).

#### 2. Planner & Reasoning Selection
- Evaluates the task's constraints against planner profiles (ADR-08).
- Selects the cheapest and fastest reasoning engine and planner combination that satisfies the required accuracy and safety thresholds.

#### 3. Stopping Criteria & Self-Evaluation
- Evaluates active executions. If a plan is determined to exceed its resource budgets or fails to reduce prediction error, Meta-Cognition aborts execution.
- **Deciding when not to answer**: If confidence is extremely low and information retrieval yields no supportive evidence, it politely declines to answer rather than speculating.
