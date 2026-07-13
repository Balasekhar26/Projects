from __future__ import annotations

import time
import uuid
from typing import Any, List, Dict

from backend.core.observability.telemetry import TelemetryCollector


def log_decision(
    stage: str,
    action: str,
    reason: str,
    alternatives: List[str] | None = None,
    confidence: float = 1.0,
    inputs: Dict[str, Any] | None = None,
    outputs: Dict[str, Any] | None = None,
    metadata: Dict[str, Any] | None = None,
) -> str:
    """Logs a cognitive decision event, attributing it to the active trace span if available."""
    decision_id = str(uuid.uuid4())
    now = time.time()

    collector = TelemetryCollector()
    active_span = collector.get_active_span()

    trace_id = active_span.trace_id if active_span else str(uuid.uuid4())
    span_id = active_span.span_id if active_span else str(uuid.uuid4())

    # Annotate active span if present
    if active_span:
        active_span.annotate(
            message=f"Decision logged: {action} (confidence={confidence})",
            stage=stage,
            reason=reason,
        )

    try:
        from backend.core.cos.kernel import KERNEL
        if KERNEL and hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
            KERNEL.ledger.record_decision(
                decision_id=decision_id,
                trace_id=trace_id,
                span_id=span_id,
                stage=stage,
                timestamp=now,
                action=action,
                reason=reason,
                alternatives=alternatives or [],
                confidence=confidence,
                inputs=inputs or {},
                outputs=outputs or {},
                metadata=metadata or {},
            )
    except Exception:
        pass

    return decision_id
