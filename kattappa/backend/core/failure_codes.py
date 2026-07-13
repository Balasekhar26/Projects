"""Structured failure reason codes for Kattappa — M38 Operational Intelligence Sprint.

Every request that does not complete successfully receives a ``FailureReason``
code attached to the ``RequestTracer`` output.  This eliminates mystery
debugging: if Kattappa says "Unable to run", the trace shows *exactly* where
and why it died.

Usage example::

    from backend.core.failure_codes import FailureReason
    tracer.finalize_failure(FailureReason.ESCALATION_BYPASSED, "Level 1 RBIL, routed to direct_model")
"""

from __future__ import annotations

from enum import Enum


class FailureReason(str, Enum):
    """Canonical failure reason codes emitted in every RequestTracer output.

    Codes
    -----
    OK
        Request completed successfully — no failure.
    NO_INTENT_MATCH
        The intent classifier could not determine an appropriate execution path
        and fell back to a generic response.
    ESCALATION_BYPASSED
        RBIL classified the request at Level 1 or 2, routing it directly to the
        model instead of the agent graph. Common cause: missing keywords in
        ``classify_escalation_level``.
    CAPABILITY_DENIED
        The requested capability was rejected by the PermissionGovernor or
        CapabilityRegistry before reaching the tool.
    NO_BACKEND_IMPLEMENTED
        The selected agent exists as a graph node but the underlying tool
        function is a stub with no real implementation.
    TOOL_EXECUTION_ERROR
        The tool backend raised an exception or returned a non-success result
        during execution (e.g. file not found, subprocess timeout).
    SAFETY_BLOCKED
        The safety monitor or policy engine blocked the action before execution.
    APPROVAL_PENDING
        The action requires human approval and is waiting on an ``approval_id``.
    CONTEXT_DRIFT
        The model's response addressed a previous message from memory context
        rather than the current request.
    DEPENDENCY_MISSING
        A required optional dependency (e.g. Playwright, pyautogui) is not
        installed in the runtime environment.
    UNKNOWN
        The failure cause could not be categorised automatically.  Investigate
        the full trace log for details.
    """

    OK                      = "OK"
    NO_INTENT_MATCH         = "NO_INTENT_MATCH"
    ESCALATION_BYPASSED     = "ESCALATION_BYPASSED"
    CAPABILITY_DENIED       = "CAPABILITY_DENIED"
    NO_BACKEND_IMPLEMENTED  = "NO_BACKEND_IMPLEMENTED"
    TOOL_EXECUTION_ERROR    = "TOOL_EXECUTION_ERROR"
    SAFETY_BLOCKED          = "SAFETY_BLOCKED"
    APPROVAL_PENDING        = "APPROVAL_PENDING"
    CONTEXT_DRIFT           = "CONTEXT_DRIFT"
    DEPENDENCY_MISSING      = "DEPENDENCY_MISSING"
    UNKNOWN                 = "UNKNOWN"


def infer_failure_reason(result_text: str, agent: str | None) -> FailureReason:
    """Heuristically infer a ``FailureReason`` from a result string.

    Used as a lightweight fallback when the caller does not explicitly set a
    failure reason.  Exact-match callers should call ``finalize_failure``
    directly instead of relying on this function.

    Parameters
    ----------
    result_text:
        The ``state["result"]`` string returned by the pipeline.
    agent:
        The agent that handled the request, if known.
    """
    if not result_text:
        return FailureReason.UNKNOWN

    lower = result_text.lower()

    if "playwright is not available" in lower or "dependency" in lower or "not installed" in lower:
        return FailureReason.DEPENDENCY_MISSING
    if "blocked" in lower or "prohibited" in lower:
        return FailureReason.SAFETY_BLOCKED
    if "approval required" in lower or "waiting for approval" in lower:
        return FailureReason.APPROVAL_PENDING
    if "drifted from your latest message" in lower or "resend the exact task" in lower:
        return FailureReason.CONTEXT_DRIFT
    if "not found" in lower or "execution error" in lower or "failed" in lower:
        return FailureReason.TOOL_EXECUTION_ERROR
    if "stub" in lower or "not implemented" in lower or "placeholder" in lower:
        return FailureReason.NO_BACKEND_IMPLEMENTED

    return FailureReason.OK
