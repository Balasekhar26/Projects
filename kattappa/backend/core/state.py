from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    user_input: str
    memory_query: str | None
    chat_session_id: str | None
    current_chat_message_id: str | None
    ephemeral_worker: bool
    plan: str | None
    selected_agent: str | None
    memory_context: str | None
    related_messages: list[dict[str, Any]]
    tool_request: dict[str, Any] | None
    approval_id: str | None
    approved_approval_id: str | None
    approval_required: bool
    risk_level: str
    result: str | None
    logs: list[str]
    operator_plan: dict[str, Any] | None
    trust_tag: str
