from __future__ import annotations

import re
from typing import Any

from backend.core.config import load_config


FREE_LOCAL_STACK = [
    "Ollama local models",
    "LangGraph orchestration",
    "ChromaDB + SQLite memory",
    "Playwright browser automation",
    "Windows UI Automation / PyAutoGUI desktop control",
    "Whisper/faster-whisper speech input",
    "Piper or pyttsx3 speech output",
]


ACTION_HINTS = {
    "screen_observation": ["observe", "watch", "look", "inspect", "analyze", "check screen", "screenshot"],
    "human_guided_step": ["guide", "show me", "where to click", "cursor", "step by step", "teach", "walk me through"],
    "approval_gated_action": [
        "click",
        "type",
        "press",
        "open app",
        "fill",
        "select",
        "do it",
        "complete it",
        "handle it",
        "automate",
        "finish the task",
    ],
}

STOP_WORDS = {
    "about",
    "after",
    "click",
    "could",
    "cursor",
    "desktop",
    "find",
    "from",
    "guide",
    "help",
    "into",
    "mode",
    "move",
    "open",
    "press",
    "please",
    "screen",
    "select",
    "show",
    "step",
    "teach",
    "that",
    "the",
    "then",
    "there",
    "this",
    "through",
    "type",
    "where",
    "with",
}


def detect_execution_path(text: str) -> str:
    lower = _strip_legacy_mode_prefix(text).lower()
    for path in ("approval_gated_action", "human_guided_step", "screen_observation"):
        if any(hint in lower for hint in ACTION_HINTS[path]):
            return path
    return "reply_only"


def build_operator_plan(
    request: str,
    selected_agent: str | None,
    memory_context: str | None = None,
    screen_text: str | None = None,
    screen_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    execution_path = detect_execution_path(request)
    config = load_config()
    if execution_path == "human_guided_step" and not config.teach_mode_enabled:
        execution_path = "screen_observation"
    needs_approval = execution_path == "approval_gated_action"
    action_required = execution_path != "reply_only"
    steps = ["Understand the order and choose the safest direct response."]

    if screen_text:
        steps.append("Use current screen text to identify likely controls and avoid blind clicks.")
    if execution_path == "reply_only":
        steps.append("Reply in English without showing extra controls or action planning.")
    elif execution_path == "screen_observation":
        steps.append("Return observations only; do not move the cursor or press keys.")
    elif execution_path == "human_guided_step":
        steps.append("Show cursor guidance and exact human steps; do not act automatically.")
    elif execution_path == "approval_gated_action":
        steps.append("Ask approval, then perform only the approved click/type/keypress action.")

    visual_guidance = build_visual_guidance(
        request=request,
        execution_path=execution_path,
        screen_snapshot=screen_snapshot,
        approval_required=needs_approval,
        enabled=config.guidance_overlay_enabled and action_required,
    )
    if visual_guidance["enabled"]:
        steps.append(str(visual_guidance["instruction"]))

    return {
        "execution_path": execution_path,
        "intent": _execution_path_label(execution_path),
        "agent": selected_agent or "evaluator",
        "goal": request,
        "local_only": True,
        "free_stack": FREE_LOCAL_STACK,
        "action_required": action_required,
        "needs_approval": needs_approval,
        "approval_policy": (
            "Required before desktop control, shell execution, file writes, installs, network actions, "
            "credentials, payments, deletion, or security changes."
        ),
        "next_steps": steps,
        "memory_used": bool(memory_context),
        "screen_context_available": bool(screen_text),
        "visual_guidance": visual_guidance,
    }


def build_visual_guidance(
    request: str,
    execution_path: str,
    screen_snapshot: dict[str, Any] | None,
    approval_required: bool,
    enabled: bool = True,
) -> dict[str, Any]:
    if not enabled or execution_path not in {"human_guided_step", "approval_gated_action"}:
        return {"enabled": False, "reason": "Visual guidance is not needed for this order."}
    if not _explicit_visual_guidance_requested(request):
        return {"enabled": False, "reason": "The order does not ask for cursor or target guidance."}

    target = _find_best_ocr_target(request, screen_snapshot)
    matched = bool(target)
    if target is None:
        return {"enabled": False, "reason": "No reliable screen target was found."}

    verb = "Review" if approval_required else "Move to"
    qualifier = "after approving this one step" if approval_required else "when you are ready"
    instruction = f"{verb} the highlighted target ({target['label']}) {qualifier}."

    return {
        "enabled": True,
        "execution_path": execution_path,
        "kind": "one_step_overlay",
        "requires_approval": approval_required,
        "matched_screen_text": matched,
        "target": target,
        "instruction": instruction,
        "safety_note": (
            "This overlay only points at one human-reviewed step. It does not move the mouse, type, click, "
            "submit, install, delete, or change settings."
        ),
    }


def _explicit_visual_guidance_requested(request: str) -> bool:
    lower = _strip_legacy_mode_prefix(request).lower()
    return any(
        phrase in lower
        for phrase in (
            "cursor",
            "highlight",
            "show me where",
            "where to click",
            "point to",
            "guide me to",
            "click",
            "select",
            "press",
            "type into",
            "open app",
        )
    )


def _find_best_ocr_target(request: str, screen_snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not screen_snapshot:
        return None
    width = int(screen_snapshot.get("width") or 0)
    height = int(screen_snapshot.get("height") or 0)
    words = screen_snapshot.get("words") or []
    if width <= 0 or height <= 0 or not isinstance(words, list):
        return None

    terms = _request_terms(request)
    if not terms:
        return None

    best: tuple[int, dict[str, Any]] | None = None
    for word in words:
        text = str(word.get("text", "")).lower()
        normalized = re.sub(r"[^a-z0-9]+", "", text)
        if not normalized:
            continue
        score = 0
        for term in terms:
            if normalized == term:
                score = max(score, 3)
            elif term in normalized or normalized in term:
                score = max(score, 1)
        if score == 0:
            continue
        left = int(word.get("left") or 0)
        top = int(word.get("top") or 0)
        box_width = max(1, int(word.get("width") or 1))
        box_height = max(1, int(word.get("height") or 1))
        confidence = int(word.get("confidence") or 0)
        candidate = {
            "label": str(word.get("text") or "screen text"),
            "x": _clamp((left + box_width / 2) / width),
            "y": _clamp((top + box_height / 2) / height),
            "width": _clamp(max(box_width / width, 0.08), maximum=0.36),
            "height": _clamp(max(box_height / height, 0.06), maximum=0.24),
            "confidence": confidence,
            "source": "ocr",
        }
        rank = score * 100 + confidence
        if best is None or rank > best[0]:
            best = (rank, candidate)
    return best[1] if best else None


def _request_terms(request: str) -> list[str]:
    clean = _strip_legacy_mode_prefix(request).lower()
    terms = []
    for raw in re.findall(r"[a-z0-9]{3,}", clean):
        if raw not in STOP_WORDS and raw not in terms:
            terms.append(raw)
    return terms[:12]


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _strip_legacy_mode_prefix(request: str) -> str:
    return re.sub(r"\[operator mode:[^\]]+\]", " ", request, flags=re.IGNORECASE)


def _execution_path_label(execution_path: str) -> str:
    return {
        "reply_only": "Reply only",
        "screen_observation": "Screen review",
        "human_guided_step": "Guided human step",
        "approval_gated_action": "Approval-gated action",
    }.get(execution_path, "Automatic route")
