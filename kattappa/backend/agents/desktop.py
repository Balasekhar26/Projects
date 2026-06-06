from __future__ import annotations

from backend.core.memory import memory
from backend.core.operator import build_operator_plan
from backend.tools.screen_tools import read_screen_snapshot


def desktop_node(state):
    screen_snapshot = read_screen_snapshot()
    screen_text = str(screen_snapshot["text"])
    operator_plan = build_operator_plan(
        state["user_input"],
        state.get("selected_agent"),
        state.get("memory_context"),
        screen_text=screen_text,
        screen_snapshot=screen_snapshot,
    )
    state["operator_plan"] = operator_plan
    guidance = operator_plan.get("visual_guidance", {})
    guidance_text = ""
    if guidance.get("enabled"):
        guidance_text = (
            "\n\nVisual one-step guidance:\n"
            f"{guidance.get('instruction')}\n"
            f"{guidance.get('safety_note')}"
        )
    if operator_plan["needs_approval"]:
        approval_id = memory.create_approval(
            f"Desktop {operator_plan['mode']} action: {state['user_input']}",
            state.get("risk_level", "medium"),
        )
        state["approval_id"] = approval_id
        state["approval_required"] = True
        state["result"] = (
            "Desktop control is ready, but I paused for your approval.\n"
            f"Mode: {operator_plan['mode']}\n"
            f"Approval id: {approval_id}\n\n"
            "Current screen text:\n\n"
            + screen_text
            + guidance_text
        )
        state["logs"].append("desktop: approval created")
        return state

    state["result"] = (
        f"Desktop {operator_plan['mode']} mode. I will guide you without controlling the mouse or keyboard.\n\n"
        "Current screen text:\n\n"
        + screen_text
        + guidance_text
    )
    state["approval_required"] = False
    state["logs"].append("desktop: guide generated")
    return state
