from __future__ import annotations
import uuid
from datetime import datetime
from backend.core.memory.memory_store import MemoryStore

class EvaluationEngine:
    @classmethod
    def record_prediction(
        cls,
        task_id: str,
        predicted_confidence: float,
        predicted_duration: float,
        predicted_memory_usage: float,
        predicted_success_probability: float
    ) -> None:
        """Records pre-task estimates in the database."""
        prediction_id = str(uuid.uuid4())
        MemoryStore.add_prediction(
            prediction_id=prediction_id,
            task_id=task_id,
            predicted_confidence=predicted_confidence,
            predicted_duration=predicted_duration,
            predicted_memory_usage=predicted_memory_usage,
            predicted_success_probability=predicted_success_probability
        )

    @classmethod
    def record_outcome(
        cls,
        task_id: str,
        actual_duration: float,
        actual_memory_usage: float,
        actual_cpu_usage: float,
        success: bool,
        failure_reason: str | None = None
    ) -> None:
        """Records execution outcomes, calculates error deltas, and updates correction factors."""
        outcome_id = str(uuid.uuid4())
        MemoryStore.add_outcome(
            outcome_id=outcome_id,
            task_id=task_id,
            actual_duration=actual_duration,
            actual_memory_usage=actual_memory_usage,
            actual_cpu_usage=actual_cpu_usage,
            success=1 if success else 0,
            failure_reason=failure_reason
        )

        # Retrieve prediction to calculate drift
        conn = MemoryStore._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM execution_predictions WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,)
        )
        pred_row = cursor.fetchone()
        
        if pred_row:
            pred = dict(pred_row)
            # Calculate drift
            actual_success_val = 1.0 if success else 0.0
            prediction_error = pred["predicted_success_probability"] - actual_success_val
            confidence_error = pred["predicted_confidence"] - actual_success_val
            resource_error = pred["predicted_memory_usage"] - actual_memory_usage

            drift_id = str(uuid.uuid4())
            MemoryStore.add_drift(
                drift_id=drift_id,
                task_id=task_id,
                prediction_error=prediction_error,
                confidence_error=confidence_error,
                resource_error=resource_error
            )

            # Recalculate average biases and update self-calibration correction factors
            cursor.execute("SELECT AVG(confidence_error) FROM confidence_drift")
            avg_conf_err_row = cursor.fetchone()
            avg_conf_err = avg_conf_err_row[0] if avg_conf_err_row and avg_conf_err_row[0] is not None else 0.0

            # Compute new correction factor (limit between 0.5 and 1.5 to prevent extreme drift scaling)
            avg_conf_err = round(avg_conf_err, 2)
            correction_factor = round(max(0.5, min(1.5, 1.0 - avg_conf_err)), 2)
            MemoryStore.update_calibration(
                metric_name="confidence",
                current_bias=avg_conf_err,
                correction_factor=correction_factor
            )

    @classmethod
    def calibrate_confidence(cls, predicted_confidence: float) -> float:
        """Scales planner prediction ratings using the current self-calibration correction factor."""
        calib = MemoryStore.get_calibration("confidence")
        if not calib:
            return round(predicted_confidence, 2)
            
        correction_factor = calib["correction_factor"]
        calibrated = predicted_confidence * correction_factor
        return round(max(0.0, min(1.0, calibrated)), 2)
