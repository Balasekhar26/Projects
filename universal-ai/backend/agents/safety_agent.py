from __future__ import annotations

from backend.core.memory import memory
from backend.core.safety import classify_risk


def safety_node(state):
    decision = classify_risk(state["user_input"])
    state["risk_level"] = decision.level
    state["approval_required"] = decision.approval_required
    state["logs"].append(f"safety: {decision.level} - {decision.reason}")
    if decision.blocked:
        state["selected_agent"] = "evaluator"
        state["result"] = "Blocked for safety. I cannot help with that action."
    elif decision.approval_required:
        approval_id = memory.create_approval(state["user_input"], decision.level)
        state["approval_id"] = approval_id
        state["result"] = f"Approval required before this action can continue. Approval id: {approval_id}"
    return state
