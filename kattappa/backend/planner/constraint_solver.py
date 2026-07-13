import time
from typing import Any, Dict, List, Optional

class ConstraintException(Exception):
    """Raised when hard constraints or budgets are violated."""
    pass


class ConstraintSolver:
    """Validates temporal budgets, execution deadlines, and operator retry thresholds."""

    @staticmethod
    def validate_temporal_constraints(
        deadline: Optional[float],
        timeout: Optional[float],
        elapsed_time: float,
        start_time: float
    ) -> None:
        """Verifies if deadlines or elapsed time run over strict threshold values."""
        now = time.time()
        
        # Check overall budget timeout limit
        if timeout is not None and elapsed_time > timeout:
            raise ConstraintException(
                f"Constraint Violated: Total elapsed planning time ({elapsed_time:.2f}s) "
                f"exceeds maximum allowed timeout parameter ({timeout:.2f}s)."
            )
            
        # Check hard timestamp deadline limit
        if deadline is not None and now > deadline:
            raise ConstraintException(
                f"Constraint Violated: Current time ({now:.2f}) is past execution deadline ({deadline:.2f})."
            )

    @staticmethod
    def validate_retry_limits(
        retry_count: int,
        max_retries: int
    ) -> None:
        """Ensures operator retry limits are not exceeded."""
        if retry_count > max_retries:
            raise ConstraintException(
                f"Constraint Violated: Current task retry count ({retry_count}) "
                f"exceeds maximum allowed threshold parameter ({max_retries})."
            )
