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
    approved: bool | None
    double_approved: bool | None
    approval_required: bool
    risk_level: str
    result: str | None
    logs: list[str]
    operator_plan: dict[str, Any] | None
    trust_tag: str
    # Cognitive pipeline keys
    observation_frame: dict[str, Any] | None
    attention_frame: dict[str, Any] | None
    memory_payload: dict[str, Any] | None
    council_debate_result: dict[str, Any] | None
    reasoning_hypothesis: str | None
    stakes_level: str
    reversibility: str
    required_confidence: float
    path_selected: str
    metacognitive_action: str
    world_model_prediction: dict[str, Any] | None
    re_retrieve_count: int
    blackboard: Any | None
    memory_confidence_level: str
    reasoning_recursion_depth: int
    reasoning_gaps: str | None
    kg_context: str | None
    goal_id: str | None

