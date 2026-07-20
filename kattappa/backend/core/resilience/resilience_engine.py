from backend.core.resilience.retry_manager import RetryManager
from backend.core.resilience.rollback_engine import RollbackEngine
from backend.core.resilience.graceful_degradation import GracefulDegradation

class ResilienceEngine:
    def __init__(self):
        self.retry_manager = RetryManager()
        self.rollback_engine = RollbackEngine()
        self.degradation = GracefulDegradation()

    def run_safe_retry(self, func, max_attempts: int = 3):
        """Executes task block with retry loops."""
        return self.retry_manager.execute_with_retry(func, max_attempts=max_attempts)

    def trigger_rollback(self, checkpoint: dict) -> dict:
        """Restores state context."""
        return self.rollback_engine.rollback_state(checkpoint)

    def determine_system_features(self, cpu_percent: float) -> list[str]:
        """Calculates allowed features under resource strain constraints."""
        return self.degradation.get_active_features(cpu_percent)
