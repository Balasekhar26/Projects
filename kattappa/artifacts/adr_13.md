# ADR-13: Agent Framework Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Running complex cognitive tasks requires specialized roles (engineering, scientific exploration, code critique, context research). Managing these as ad-hoc prompt templates or loose pipelines leads to memory leaks, state mismatches, and coordination bottlenecks.

### Decision
Define a unified, role-based **Agent Framework** where specialized agents operate as first-class cognitive threads coordinated by a central scheduler.

---

### Core Data Structures & Specs

```python
class CognitiveAgent:
    agent_id: str
    role_name: str           # e.g., 'planner', 'scientist', 'critic', 'engineer'
    working_memory_ref: str  # Isolated working memory stack reference
    mailbox: Queue[Message]  # Inbox for structured inter-agent messages
    status: str              # SPAWNING, ACTIVE, SUSPENDED, RETIRED
```

---

### Agent Roles Taxonomy

1. **Planner**: Computes state path searches and creates execution DAGs.
2. **Scientist**: Designs experiments, generates hypotheses, and updates belief priors.
3. **Engineer**: Writes code, fixes tests, and creates file structures.
4. **Critic / Reviewer**: Validates plan outputs and tests correctness.
5. **Researcher**: Queries long-term semantic indices and crawls sources.
6. **Coordinator**: Orchestrates message routing and arbitrates conflicts between agents.

---

### Lifecycle & Collaboration Rules
- **Spawning & Retirement**: The Executive Controller spawns agents dynamically to execute specific subgoals. When a subgoal is completed, the agent writes its findings to long-term memory and is retired.
- **Message Exchange**: Agents communicate by passing immutable, typed `Message` objects containing schema-validated payloads:
  ```python
  class Message:
      message_id: str
      sender_id: str
      recipient_id: str
      topic: str
      payload: Dict[str, Any]
      timestamp: float
  ```
- **Memory Ownership**: An agent owns its local working memory stack. It cannot mutate another agent's working memory directly; all sharing occurs via the Blackboard or explicit message passing.
