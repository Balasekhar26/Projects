# ADR-12: Tool & Skill System Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Kattappa needs to invoke external tools and learn new procedural skills. Executing arbitrary commands or APIs without a formalized registry, cost estimations, permissions, or reliability tracking leads to security breaches, runaway budget costs, and fragile execution paths.

### Decision
Define a unified, secure **Tool & Skill System** structured around a central registry with cost estimation, security permissions, and reliability feedback loops.

---

### Core Data Structures & Specs

```python
class ToolSignature:
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    return_schema: Dict[str, Any]
    required_permissions: List[str]  # e.g., 'filesystem.read', 'network.outbound'
    cost_estimation_coef: float     # Estimated baseline token/USD cost
    expected_latency: float          # Baseline latency in seconds
    embedding: List[float]           # 1536D vector representing tool capability semantic
```

```python
class ToolRegistry:
    """Central interface managing available tools, skills, and invocation policies."""
    tools: Dict[str, ToolSignature]
    reliability_scores: Dict[str, float]  # tracks F1 failure rates per tool
    invocation_counts: Dict[str, int]
```

---

### Key Execution Policies
1. **Tool Selection Heuristic**: Selection matches semantic embedding similarity with task goal description, discounted by tool reliability:
   $$\text{Utility} = \text{CosineSimilarity}(\text{ToolEmbedding}, \text{GoalEmbedding}) \times \text{ReliabilityScore}$$
2. **Retry & Backoff**: Failed tool executions trigger exponential backoff retry logic. If a tool fails 3 consecutive times, its reliability score is penalized by 15%, triggering meta-cognition to seek alternatives or alert the user.
3. **Execution Sandboxing**: All tool invocations must validate caller permissions against `required_permissions` before running. High-risk actions trigger human approval checkpoints.
