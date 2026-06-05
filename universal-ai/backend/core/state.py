from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    user_input: str
    plan: str | None
    selected_agent: str | None
    memory_context: str | None
    tool_request: dict[str, Any] | None
    approval_id: str | None
    approval_required: bool
    risk_level: str
    result: str | None
    logs: list[str]
    operator_plan: dict[str, Any] | None
