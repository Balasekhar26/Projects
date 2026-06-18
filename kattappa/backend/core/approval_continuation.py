from __future__ import annotations

import json
import re
from typing import Any

from backend.core.installer import run_approved_install_job
from backend.core.memory import memory
from backend.core.tool_adoption import continue_tool_adoption_for_approval


CHAT_CONTINUATION_TYPES = {"chat", "desktop"}
NON_CHAT_CONTINUATION_TYPES = {
    "install_job",
    "tool_adoption",
    "self_improvement",
    "self_evolution",
}


def continue_approved_work(approval_id: str) -> dict[str, Any]:
    approval = memory.get_approval(approval_id)
    if approval is None:
        return {"kind": "unknown", "status": "approval_missing", "message": "Approval missing."}
    if approval["status"] == "rejected":
        return {"kind": _approval_kind(approval), "status": "rejected", "approval": approval, "message": "Rejected."}
    if approval["status"] != "approved":
        return {
            "kind": _approval_kind(approval),
            "status": "waiting_for_approval",
            "approval": approval,
            "message": "Waiting for approval.",
        }
    if approval.get("continued_at"):
        return {
            "kind": _approval_kind(approval),
            "status": "already_continued",
            "approval": approval,
            "message": "Already continued.",
            "previous_result": _json_or_text(approval.get("continuation_result", "")),
        }

    kind = _approval_kind(approval)
    if kind == "install_job":
        result = {"kind": "install_job", **run_approved_install_job(approval_id)}
        return _record_non_chat_continuation(approval_id, result)
    if kind == "tool_adoption":
        result = {"kind": "tool_adoption", **continue_tool_adoption_for_approval(approval_id)}
        return _record_non_chat_continuation(approval_id, result)
    if kind == "self_improvement":
        return _continue_self_improvement(approval)
    if kind == "self_evolution":
        return _continue_self_evolution(approval)
    return continue_approved_chat(approval_id)


def continue_approved_chat(approval_id: str) -> dict[str, Any]:
    approval = memory.get_approval(approval_id)
    if approval is None:
        return {"kind": "chat", "status": "approval_missing", "message": "Approval missing."}
    if approval["status"] == "rejected":
        return {"kind": "chat", "status": "rejected", "approval": approval, "message": "Rejected."}
    if approval["status"] != "approved":
        return {
            "kind": "chat",
            "status": "waiting_for_approval",
            "approval": approval,
            "message": "Waiting for approval.",
        }
    if _is_non_chat_continuation(approval):
        return {
            "kind": "chat",
            "status": "not_chat_continuation",
            "approval": approval,
            "message": "Different follow-up pipeline.",
        }

    message = _continuation_message(approval)
    if not message:
        return {
            "kind": "chat",
            "status": "not_chat_continuation",
            "approval": approval,
            "message": "No resumable chat task.",
        }

    payload = _continuation_payload(approval)
    chat_session = memory.get_or_create_primary_chat_session()
    chat_session_id = str(payload.get("chat_session_id") or chat_session["id"])
    current_message_id = str(payload.get("chat_message_id") or "") or None
    memory_query = str(payload.get("memory_query") or message)

    from backend.core.graph import run_graph

    state = run_graph(
        message,
        approved_approval_id=approval_id,
        chat_session_id=chat_session_id,
        current_chat_message_id=current_message_id,
        memory_query=memory_query,
    )
    response = str(state.get("result") or "")
    memory.add_chat_message(
        chat_session["id"],
        "assistant",
        response,
        agent=str(state.get("selected_agent") or ""),
        risk=str(state.get("risk_level") or ""),
    )
    updated_approval = memory.record_approval_continuation(approval_id, response) or approval
    return {
        "kind": "chat",
        "status": "completed",
        "approval": updated_approval,
        "response": response,
        "state": state,
    }


def _approval_kind(approval: dict[str, str]) -> str:
    continuation_type = approval.get("continuation_type") or "manual"
    if continuation_type in CHAT_CONTINUATION_TYPES | NON_CHAT_CONTINUATION_TYPES:
        return continuation_type
    if memory.get_install_job(approval["id"]) is not None:
        return "install_job"
    if memory.get_tool_adoption_job_by_approval(approval["id"]) is not None:
        return "tool_adoption"
    action = approval["action"]
    if action.startswith("Review self-improvement proposal"):
        return "self_improvement"
    if action.startswith("Review and approve draft self-evolution skill"):
        return "self_evolution"
    if action.startswith("Install missing free/local Kattappa AI OS capabilities."):
        return "install_job"
    if action.startswith("Approve install/run stage") or action.startswith("Final approval to add staged capability"):
        return "tool_adoption"
    return "chat"


def _is_non_chat_continuation(approval: dict[str, str]) -> bool:
    kind = _approval_kind(approval)
    if kind in NON_CHAT_CONTINUATION_TYPES:
        return True
    if memory.get_install_job(approval["id"]) is not None:
        return True
    if memory.get_tool_adoption_job_by_approval(approval["id"]) is not None:
        return True
    if kind not in CHAT_CONTINUATION_TYPES | {"manual", "chat"}:
        return True

    action = approval["action"]
    legacy_non_chat_prefixes = (
        "Review self-improvement proposal",
        "Review and approve draft self-evolution skill",
        "Install missing free/local Kattappa AI OS capabilities.",
        "Approve install/run stage",
        "Final approval to add staged capability",
    )
    return (approval.get("continuation_type") or "manual") == "manual" and action.startswith(legacy_non_chat_prefixes)


def _continue_self_improvement(approval: dict[str, str]) -> dict[str, Any]:
    payload = _continuation_payload(approval)
    improvement_id = str(payload.get("improvement_id") or _match_after(approval["action"], "proposal") or "")
    skill_id = str(payload.get("skill_id") or _match_after(approval["action"], "draft skill") or "")
    if not improvement_id:
        result = {
            "kind": "self_improvement",
            "status": "missing_payload",
            "approval": approval,
            "message": "Self-improvement approval has no linked improvement id.",
        }
        return _record_non_chat_continuation(approval["id"], result)

    improvement = memory.update_improvement(improvement_id, "approved")
    skill = memory.update_skill_trust(skill_id, "approved") if skill_id else None
    if skill_id and skill is not None:
        memory.create_skill_evaluation(
            skill_id=skill_id,
            result="pass",
            score=80,
            notes="Approved by Bala; ready for approved self-improvement execution.",
        )
    result = {
        "kind": "self_improvement",
        "status": "continued",
        "approval": approval,
        "improvement": improvement,
        "skill": skill,
        "message": (
            "Self-improvement approval continued: proposal approved, draft skill approved, "
            "and the work is queued for the next approved implementation step. No code files were modified automatically."
        ),
    }
    return _record_non_chat_continuation(approval["id"], result)


def _continue_self_evolution(approval: dict[str, str]) -> dict[str, Any]:
    payload = _continuation_payload(approval)
    skill_id = str(payload.get("skill_id") or _match_after(approval["action"], "skill") or "")
    if not skill_id:
        result = {
            "kind": "self_evolution",
            "status": "missing_payload",
            "approval": approval,
            "message": "Self-evolution approval has no linked skill id.",
        }
        return _record_non_chat_continuation(approval["id"], result)
    skill = memory.update_skill_trust(skill_id, "approved")
    if skill is not None:
        memory.create_skill_evaluation(
            skill_id=skill_id,
            result="pass",
            score=75,
            notes="Draft self-evolution skill approved by Bala and ready for use.",
        )
    result = {
        "kind": "self_evolution",
        "status": "continued" if skill is not None else "skill_missing",
        "approval": approval,
        "skill": skill,
        "message": (
            "Self-evolution approval continued: the draft skill is now approved and ready for use."
            if skill is not None
            else "Self-evolution approval could not find the linked skill."
        ),
    }
    return _record_non_chat_continuation(approval["id"], result)


def _record_non_chat_continuation(approval_id: str, result: dict[str, Any]) -> dict[str, Any]:
    safe_result = json.dumps(result, default=str)
    updated_approval = memory.record_approval_continuation(approval_id, safe_result)
    result["approval"] = updated_approval or result.get("approval")
    _record_continuation_message(result)
    return result


def _record_continuation_message(result: dict[str, Any]) -> None:
    message = str(result.get("message") or f"Approval continuation {result.get('status', 'completed')}.")
    session = memory.get_or_create_primary_chat_session()
    memory.add_chat_message(
        session["id"],
        "assistant",
        message,
        agent="approval",
        risk=str((result.get("approval") or {}).get("risk", "")) if isinstance(result.get("approval"), dict) else "",
    )


def _match_after(action: str, label: str) -> str:
    pattern = rf"{re.escape(label)}\s+([0-9a-fA-F-]{{36}})"
    match = re.search(pattern, action)
    return match.group(1) if match else ""


def _json_or_text(text: str) -> object:
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text



def _continuation_message(approval: dict[str, str]) -> str:
    payload = _continuation_payload(approval)
    message = str(payload.get("message") or "").strip()
    if message:
        return message
    if approval.get("continuation_type") == "manual":
        return approval["action"]
    return ""


def _continuation_payload(approval: dict[str, str]) -> dict[str, object]:
    try:
        loaded = json.loads(approval.get("continuation_payload") or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}
