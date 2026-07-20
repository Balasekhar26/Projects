import time
import threading
from backend.core.autonomy.goal_manager import GoalManager, Goal
from backend.core.autonomy.scheduler import GoalScheduler

class AutonomyEngine:
    def __init__(self):
        self.manager = GoalManager()
        self.scheduler = GoalScheduler()
        self.is_running = False
        self._thread = None
        self.replans_triggered = 0

    def start(self) -> None:
        """Starts the autonomous goal watchdog thread loop."""
        self.is_running = True
        self._thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stops the autonomous watchdog thread loop."""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _watchdog_loop(self) -> None:
        """Ticks repeatedly checking active goal conditions, retries, and replanning triggers."""
        while self.is_running:
            self.manager.cleanup_expired_goals()
            active_goals = self.manager.get_active_goals()
            
            for goal in active_goals:
                if self.scheduler.should_execute(goal):
                    self._execute_goal(goal)
                    
            time.sleep(0.1) # Responsive test tick interval

    def _execute_goal(self, goal: Goal) -> None:
        """Executes a goal, handles status transitions, and triggers replanners on failure."""
        self.manager.update_goal_state(goal.goal_id, "RUNNING")
        
        # Simulates task loop execution. If the objective fails:
        # (e.g., mock failure logic if word "fail" is in objective)
        if "fail" in goal.objective.lower():
            goal.current_retry += 1
            self.manager.update_goal_state(goal.goal_id, "FAILED")
            
            # Watchdog replanning logic trigger
            if goal.current_retry < goal.max_retries:
                self.replans_triggered += 1
        else:
            self.manager.update_goal_state(goal.goal_id, "SUCCESS")
