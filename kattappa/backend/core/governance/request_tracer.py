from __future__ import annotations
import time
import logging
import uuid
import threading
from typing import Any, Optional

from backend.core.failure_codes import FailureReason, infer_failure_reason

logger = logging.getLogger(__name__)

GLOBAL_TRACES: list[dict] = []
TRACES_LOCK = threading.Lock()
MAX_TRACES = 200


class RequestTracer:
    def __init__(self, input_text: str, mode: str = "AUTO") -> None:
        self.trace_id = str(uuid.uuid4())[:8]
        self.input = input_text
        self.mode = mode
        self.intent = "UNKNOWN"
        self.router = "UNKNOWN"
        self.model = "UNKNOWN"
        self.tools: list[str] = []
        self.capabilities: list[str] = []
        self.policy = "UNKNOWN"
        self.result: Any = None
        self.start_time = time.perf_counter()
        self.latency_ms = 0.0
        # M38: structured failure reason code
        self.failure_reason: FailureReason = FailureReason.UNKNOWN
        self.failure_detail: str = ""

    def record_stage(
        self,
        intent: Optional[str] = None,
        router: Optional[str] = None,
        model: Optional[str] = None,
        tool: Optional[str] = None,
        capability: Optional[str] = None,
        policy: Optional[str] = None,
        result: Optional[Any] = None,
    ) -> None:
        if intent:
            self.intent = intent
        if router:
            self.router = router
        if model:
            self.model = model
        if tool and tool not in self.tools:
            self.tools.append(tool)
        if capability and capability not in self.capabilities:
            self.capabilities.append(capability)
        if policy:
            self.policy = policy
        if result is not None:
            self.result = result

    def finalize_failure(
        self,
        reason: FailureReason,
        detail: str = "",
        result: Optional[Any] = None,
    ) -> None:
        """Explicitly mark this trace with a structured failure reason code.

        Call this instead of ``finalize()`` whenever a known failure mode is
        detected so that the reason code is exact rather than inferred.

        Parameters
        ----------
        reason:
            The ``FailureReason`` enum value describing why the request failed.
        detail:
            A short human-readable explanation (shown in the trace output).
        result:
            Optional final result text to attach to the trace.
        """
        self.failure_reason = reason
        self.failure_detail = detail
        if result is not None:
            self.result = result
        self.latency_ms = (time.perf_counter() - self.start_time) * 1000.0
        self.print_trace()

    def finalize(self, result: Optional[Any] = None) -> None:
        if result is not None:
            self.result = result
        self.latency_ms = (time.perf_counter() - self.start_time) * 1000.0
        # M38: auto-infer failure reason when not explicitly set
        if self.failure_reason == FailureReason.UNKNOWN:
            self.failure_reason = infer_failure_reason(
                str(self.result) if self.result else "",
                agent=self.router if self.router != "UNKNOWN" else None,
            )
        self.print_trace()

    def print_trace(self) -> None:
        result_str = str(self.result) if self.result else "None"
        result_display = result_str[:200] + "..." if len(result_str) > 200 else result_str
        failure_display = self.failure_reason.value
        if self.failure_detail:
            failure_display += f"  ({self.failure_detail})"
        trace_str = (
            f"\n"
            f"==================================================\n"
            f"KATTAPPA REQUEST TRACE: {self.trace_id}\n"
            f"==================================================\n"
            f"INPUT:          {self.input}\n"
            f"MODE:           {self.mode}\n"
            f"INTENT:         {self.intent}\n"
            f"ROUTER:         {self.router}\n"
            f"MODEL:          {self.model}\n"
            f"TOOLS:          {', '.join(self.tools) if self.tools else 'None'}\n"
            f"CAPABILITIES:   {', '.join(self.capabilities) if self.capabilities else 'None'}\n"
            f"POLICY:         {self.policy}\n"
            f"FAILURE_REASON: {failure_display}\n"
            f"RESULT:         {result_display}\n"
            f"LATENCY:        {self.latency_ms:.2f} ms\n"
            f"=================================================="
        )
        try:
            import sys as _sys
            if hasattr(_sys.stdout, "buffer"):
                _sys.stdout.buffer.write((trace_str + "\n").encode("utf-8", errors="replace"))
                _sys.stdout.buffer.flush()
            else:
                print(trace_str.encode("ascii", errors="replace").decode("ascii"), flush=True)
        except Exception:
            pass
        logger.info(trace_str)

        # Record trace for dashboard
        trace_data = {
            "trace_id": self.trace_id,
            "input": self.input,
            "mode": self.mode,
            "intent": self.intent,
            "router": self.router,
            "model": self.model,
            "tools": list(self.tools),
            "capabilities": list(self.capabilities),
            "policy": self.policy,
            "result": str(self.result) if self.result is not None else "",
            "failure_reason": self.failure_reason.value if hasattr(self.failure_reason, "value") else str(self.failure_reason),
            "failure_detail": self.failure_detail,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": time.time(),
        }
        with TRACES_LOCK:
            GLOBAL_TRACES.append(trace_data)
            if len(GLOBAL_TRACES) > MAX_TRACES:
                GLOBAL_TRACES.pop(0)

