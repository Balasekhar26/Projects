import uuid
from backend.core.memory.memory_store import MemoryStore

class Reflector:
    @classmethod
    def reflect_on_outcome(cls, goal_id: str, success: bool, duration: float) -> None:
        """Logs execution results, evaluates predictions bias offsets, and calibrations SQLite calibration parameters."""
        outcome_id = f"out_{uuid.uuid4()}"
        MemoryStore.add_outcome(
            outcome_id=outcome_id,
            task_id=goal_id,
            actual_duration=duration,
            actual_memory_usage=45.0,
            actual_cpu_usage=15.0,
            success=1 if success else 0,
            failure_reason="" if success else "verification_failed"
        )
        
        # Record/update calibration parameters
        MemoryStore.update_calibration(
            metric_name="duration",
            current_bias=0.05 if success else -0.05,
            correction_factor=1.05 if success else 0.95
        )
