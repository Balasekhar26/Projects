from __future__ import annotations

import json

from backend.core.memory import memory
from backend.core.operator import build_operator_plan
from backend.tools.screen_tools import read_screen_snapshot


def desktop_node(state):
    screen_snapshot = read_screen_snapshot()
    screen_text = str(screen_snapshot["text"])
    usable_screen_text = screen_text if _screen_text_is_usable(screen_text, screen_snapshot) else ""
    operator_plan = build_operator_plan(
        state["user_input"],
        state.get("selected_agent"),
        state.get("memory_context"),
        screen_text=usable_screen_text,
        screen_snapshot=screen_snapshot,
    )
    state["operator_plan"] = operator_plan
    guidance = operator_plan.get("visual_guidance", {})
    guidance_text = ""
    if guidance.get("enabled"):
        guidance_text = (
            "\nNext: "
            f"{guidance.get('instruction')}"
        )
    if operator_plan["needs_approval"] and not _approved_desktop_continuation_matches(
        str(state.get("approved_approval_id") or ""),
        state["user_input"],
    ):
        approval_id = memory.create_approval(
            f"Desktop action: {state['user_input']}",
            state.get("risk_level", "medium"),
            continuation_type="desktop",
            continuation_payload=json.dumps(
                {
                    "message": state["user_input"],
                    "memory_query": state.get("memory_query") or state["user_input"],
                    "chat_session_id": state.get("chat_session_id"),
                    "chat_message_id": state.get("current_chat_message_id"),
                    "source": "desktop",
                    "execution_path": operator_plan["execution_path"],
                }
            ),
        )
        state["approval_id"] = approval_id
        state["approval_required"] = True
        state["result"] = _desktop_response(
            "Approval needed for desktop control. Approve to continue.",
            usable_screen_text,
            guidance_text,
        )
        state["logs"].append("desktop: approval created")
        return state

    state["result"] = _desktop_response(
        "Tell me the visible target/window and I will guide the next step.",
        usable_screen_text,
        guidance_text,
    )
    state["approval_required"] = False
    state["logs"].append("desktop: guide generated")
    return state


def _desktop_response(base: str, screen_text: str, guidance_text: str) -> str:
    parts = [base]
    screen_summary = _screen_summary(screen_text)
    if screen_summary:
        parts.append(f"Screen: {screen_summary}")
    if guidance_text:
        parts.append(guidance_text.strip())
    return "\n".join(parts)


def _screen_text_is_usable(text: str, snapshot: dict[str, object]) -> bool:
    clean = " ".join(text.split())
    if not clean:
        return False
    if clean.startswith("Screen capture unavailable:"):
        return False
    if clean.startswith("Screenshot saved to"):
        return False
    return bool(snapshot.get("words") or len(clean) >= 3)


def _screen_summary(text: str, limit: int = 360) -> str:
    clean = " ".join(text.split())
    if not clean:
        return ""
    if clean.startswith("Screen capture unavailable:"):
        return ""
    if clean.startswith("Screenshot saved to") and "OCR failed" in clean:
        return ""
    if clean.startswith("Screenshot saved to") and "no OCR text found" in clean:
        return ""
    return clean if len(clean) <= limit else f"{clean[:limit].rstrip()}..."


def _approved_desktop_continuation_matches(approval_id: str, message: str) -> bool:
    if not approval_id:
        return False
    approval = memory.get_approval(approval_id)
    if not approval or approval["status"] != "approved":
        return False
    if approval["continuation_type"] not in {"chat", "desktop", "manual"}:
        return False
    try:
        payload = json.loads(approval.get("continuation_payload") or "{}")
    except json.JSONDecodeError:
        payload = {}
    return str(payload.get("message") or approval["action"]) == message
