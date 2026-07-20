from datetime import datetime, timedelta
from dataclasses import dataclass, field

@dataclass
class Goal:
    goal_id: str
    objective: str
    priority: int = 1
    deadline: datetime | None = None
    success_conditions: list[str] = field(default_factory=list)
    failure_conditions: list[str] = field(default_factory=list)
    retry_interval_sec: int = 5
    max_retries: int = 3
    current_retry: int = 0
    current_state: str = "PENDING"  # PENDING, RUNNING, SUCCESS, FAILED
    persistence_level: str = "DAILY" # EPHEMERAL, SESSION, DAILY, PROJECT, PERMANENT
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

class GoalManager:
    def __init__(self):
        self.goals = {}

    def register_goal(self, goal: Goal) -> None:
        """Registers a new goal in the autonomy registry."""
        self.goals[goal.goal_id] = goal

    def get_goal(self, goal_id: str) -> Goal | None:
        """Retrieves a goal by its identifier."""
        return self.goals.get(goal_id)

    def update_goal_state(self, goal_id: str, state: str) -> None:
        """Updates the state of a registered goal and refreshes its timestamp."""
        if goal_id in self.goals:
            self.goals[goal_id].current_state = state
            self.goals[goal_id].updated_at = datetime.now()

    def get_active_goals(self) -> list[Goal]:
        """Returns all goals that are not yet resolved (PENDING or RUNNING)."""
        return [g for g in self.goals.values() if g.current_state in ("PENDING", "RUNNING")]

    def cleanup_expired_goals(self) -> None:
        """Flushes expired visual goals based on their persistence levels."""
        now = datetime.now()
        expired_ids = []
        for goal_id, goal in self.goals.items():
            duration = now - goal.created_at
            if goal.persistence_level == "EPHEMERAL" and duration > timedelta(minutes=5):
                expired_ids.append(goal_id)
            elif goal.persistence_level == "SESSION" and duration > timedelta(hours=4):
                expired_ids.append(goal_id)
            elif goal.persistence_level == "DAILY" and duration > timedelta(days=1):
                expired_ids.append(goal_id)
                
        for gid in expired_ids:
            del self.goals[gid]
