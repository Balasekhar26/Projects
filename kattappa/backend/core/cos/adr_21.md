# ADR-21: Self Model Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
An autonomous agent must represent its own capabilities, limitations, and resource levels. Without an explicit, queryable **Self Model**, Kattappa cannot evaluate whether it has the tools to fulfill a request, whether it is running out of budget context, or what task milestones it has accomplished historically.

### Decision
Define a dedicated `SelfModel` entity subclass registered inside the main world coordinator that tracks installed tools, resource boundaries, historical performance, and limitations.

---

### Core Data Structure Specification

```python
class SelfModel:
    identity_uuid: str
    system_version: str
    
    # 1. Resource Boundaries & Budget
    token_budget_limit: int
    tokens_consumed: int
    execution_tick_limit_ms: float
    
    # 2. Installed Capabilities
    installed_tools: List[str]       # Registered tool IDs
    learned_skills: List[str]        # Procedural templates
    
    # 3. Working Context
    active_goals: List[str]          # Node references from Goal hierarchy
    active_tasks: List[str]          # Action queue pointers
    
    # 4. Historical Performance
    total_cycles_executed: int
    prediction_error_moving_avg: float
    historical_task_success_rate: float
    
    # 5. Knowledge Boundaries
    confidence_calibration: float    # Expected vs empirical accuracy ratio
    unresolved_contradictions_count: int
```

---

### Self-Introspection Rules
- Before accepting a high-level goal, the meta-cognition controller queries `SelfModel` to verify if required tool signatures are present in `installed_tools`. If not, it requests user delegation or triggers the Scientist agent to learn the skill.
- The `SelfModel` is updated atomically at the end of each cognitive cycle tick.
