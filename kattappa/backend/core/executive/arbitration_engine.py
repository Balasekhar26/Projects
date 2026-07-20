from backend.core.autonomy.goal_manager import Goal

class ArbitrationEngine:
    def __init__(self):
        pass

    def should_interrupt(self, current_active_priority: int, incoming_priority: int) -> bool:
        """Determines if a critical incoming goal should preempt the active task thread."""
        return incoming_priority > current_active_priority

    def resolve_conflicts(self, goals: list[Goal], utilities: dict[str, float]) -> list[Goal]:
        """Resolves competing goals by sorting them based on calculated executive utilities."""
        # Sort goals based on pre-calculated utility scores (highest utility first)
        sorted_goals = sorted(
            goals,
            key=lambda g: utilities.get(g.goal_id, 0.0),
            reverse=True
        )
        return sorted_goals
