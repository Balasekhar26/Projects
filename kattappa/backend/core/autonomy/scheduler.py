from datetime import datetime, timedelta
from backend.core.autonomy.goal_manager import Goal

class GoalScheduler:
    def __init__(self):
        pass

    def should_execute(self, goal: Goal) -> bool:
        """Determines if a goal is scheduled to execute based on state and retry intervals."""
        if goal.current_state == "PENDING":
            return True
            
        if goal.current_state == "FAILED" and goal.current_retry < goal.max_retries:
            next_run = goal.updated_at + timedelta(seconds=goal.retry_interval_sec)
            return datetime.now() >= next_run
            
        return False
