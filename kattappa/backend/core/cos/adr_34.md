# ADR-34: Long-Horizon Goal Manager Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Autonomous agents running over long periods (days/weeks) lose track of high-level missions, get stuck in local execution loops, or fail to order subtasks based on topological dependencies.

### Decision
Define a robust **Long-Horizon Goal Manager** that models goals as hierarchical trees with explicit milestones, deadlines, and dependencies.

---

### Core Data Structure Specification

```python
class GoalNode:
    goal_id: str
    parent_goal_id: Optional[str]
    description: str
    priority: int                   # e.g., 0 (reflex) to 10 (mission level)
    dependencies: List[str]         # list of sibling goal IDs that must complete first
    deadline: Optional[float]       # absolute timestamp threshold
    status: str                     # PENDING, ACTIVE, COMPLETED, FAILED, BLOCKED
    progress_percentage: float
```

---

### Key Execution Policies
1. **Topological Scheduling**: The planner only schedules actions targeting GoalNodes whose dependencies are marked `COMPLETED`.
2. **Progress Verification**: When a subtask concludes, the Goal Manager re-evaluates parent milestones. If progress stalls or a deadline is violated, it triggers meta-cognition to replan.
3. **Task Suspension**: Active lower-priority goals are automatically suspended and swapped to the database if a higher-priority milestone enters the queue.
