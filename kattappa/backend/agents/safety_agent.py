from __future__ import annotations

import json

from backend.core.memory import memory
from backend.core.safety import classify_risk


def safety_node(state):
    decision = classify_risk(state["user_input"], trust_tag=state.get("trust_tag", "SYSTEM_TRUST"))
    state["risk_level"] = decision.level
    state["approval_required"] = state.get("approval_required") or decision.approval_required
    state["logs"].append(f"safety: {decision.level} - {decision.reason}")
    if decision.blocked:
        state["selected_agent"] = "evaluator"
        state["result"] = "Blocked for safety. I cannot help with that action."
    elif decision.approval_required:
        approved_id = state.get("approved_approval_id")
        if approved_id and _approved_continuation_matches(str(approved_id), state["user_input"]):
            state["approval_required"] = False
            state["risk_level"] = f"approved:{decision.level}"
            state["logs"].append(f"safety: approved continuation {approved_id}")
            return state

        approval_id = memory.create_approval(
            state["user_input"],
            decision.level,
            continuation_type="chat",
            continuation_payload=json.dumps(
                {
                    "message": state["user_input"],
                    "memory_query": state.get("memory_query") or state["user_input"],
                    "chat_session_id": state.get("chat_session_id"),
                    "chat_message_id": state.get("current_chat_message_id"),
                    "source": "safety",
                }
            ),
        )
        state["approval_id"] = approval_id
        state["result"] = "Approval needed. Approve to continue."
    return state


def _approved_continuation_matches(approval_id: str, message: str) -> bool:
    approval = memory.get_approval(approval_id)
    if not approval or approval["status"] != "approved":
        return False
    if approval["continuation_type"] not in {"chat", "desktop", "manual"}:
        return False
    try:
        payload = json.loads(approval.get("continuation_payload") or "{}")
    except json.JSONDecodeError:
        payload = {}
    approved_message = str(payload.get("message") or approval["action"])
    return approved_message == message
