from typing import Any, Dict, List, Optional, Tuple

class GoalItem:
    """Represents a goal entry in the prioritized goal stack."""

    def __init__(
        self,
        goal_id: str,
        name: str,
        priority: str,  # "HIGH", "MEDIUM", "LOW"
        utility_score: float,
        hard_constraints: Optional[Dict[str, Any]] = None,
        soft_constraints: Optional[Dict[str, Any]] = None
    ) -> None:
        self.goal_id = goal_id
        self.name = name
        self.priority = priority
        self.utility_score = utility_score
        self.hard_constraints = dict(hard_constraints or {})
        self.soft_constraints = dict(soft_constraints or {})

    def get_sorting_key(self) -> Tuple[int, float]:
        """Calculates priority sorting order. High priority takes precedence, then utility."""
        priority_map = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        priority_num = priority_map.get(self.priority.upper(), 0)
        return (priority_num, self.utility_score)


class GoalStack:
    """Priority queue goal stack enforcing hard budget/security constraints and user preferences."""

    def __init__(self) -> None:
        self.stack: List[GoalItem] = []

    def push(self, goal: GoalItem) -> None:
        """Pushes a goal onto the stack, re-sorting based on priority keys."""
        self.stack.append(goal)
        # Sort descending (highest key first)
        self.stack.sort(key=lambda item: item.get_sorting_key(), reverse=True)

    def pop(self) -> Optional[GoalItem]:
        """Pops the highest priority goal item off the stack."""
        if not self.stack:
            return None
        return self.stack.pop(0)

    def peek(self) -> Optional[GoalItem]:
        """Peeks at the highest priority goal item without removing it."""
        if not self.stack:
            return None
        return self.stack[0]

    def size(self) -> int:
        return len(self.stack)

    def clear(self) -> None:
        self.stack.clear()
