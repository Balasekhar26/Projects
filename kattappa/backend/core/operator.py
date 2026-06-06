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


MODE_HINTS = {
    "teach": ["teach", "walk me through", "training mode", "lesson mode"],
    "guide": ["guide", "show me", "where to click", "cursor", "step by step"],
    "assist": ["click", "type", "press", "open app", "fill", "select"],
    "autonomous": ["do it", "complete it", "handle it", "automate", "finish the task"],
    "observe": ["observe", "watch", "look", "inspect", "analyze", "check screen"],
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


def detect_operator_mode(text: str) -> str:
    lower = text.lower()
    for mode in ("observe", "teach", "guide", "assist", "autonomous"):
        if f"[operator mode: {mode}]" in lower:
            return mode
    for mode, hints in MODE_HINTS.items():
        if any(hint in lower for hint in hints):
            return mode
    return "guide"


def build_operator_plan(
    request: str,
    selected_agent: str | None,
    memory_context: str | None = None,
    screen_text: str | None = None,
    screen_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode = detect_operator_mode(request)
    config = load_config()
    if mode == "teach" and not config.teach_mode_enabled:
        mode = "guide"
    needs_approval = mode in {"assist", "autonomous"}
    steps = [
        "Understand the user goal and current context.",
        "Use only free/local tools unless the user explicitly changes that rule.",
        "Explain the next action before touching the system.",
    ]

    if screen_text:
        steps.append("Use current screen text to identify likely controls and avoid blind clicks.")
    if mode == "observe":
        steps.append("Return observations only; do not move the cursor or press keys.")
    elif mode == "teach":
        steps.append("Show one visual target and explain why it is the next safe human step.")
    elif mode == "guide":
        steps.append("Show cursor guidance and exact human steps; do not act automatically.")
    elif mode == "assist":
        steps.append("Ask approval, then perform only the approved click/type/keypress action.")
    else:
        steps.append("Break the task into small approved actions and stop at each risky boundary.")

    visual_guidance = build_visual_guidance(
        request=request,
        mode=mode,
        screen_snapshot=screen_snapshot,
        approval_required=needs_approval,
        enabled=config.guidance_overlay_enabled,
    )
    if visual_guidance["enabled"]:
        steps.append(str(visual_guidance["instruction"]))

    return {
        "mode": mode,
        "agent": selected_agent or "evaluator",
        "goal": request,
        "local_only": True,
        "free_stack": FREE_LOCAL_STACK,
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
    mode: str,
    screen_snapshot: dict[str, Any] | None,
    approval_required: bool,
    enabled: bool = True,
) -> dict[str, Any]:
    safe_mode = mode in {"teach", "guide", "assist", "autonomous"}
    if not enabled or not safe_mode:
        return {"enabled": False, "reason": "Visual guidance is disabled for this mode."}

    target = _find_best_ocr_target(request, screen_snapshot)
    matched = bool(target)
    if target is None:
        target = {
            "label": "next safe area",
            "x": 0.5,
            "y": 0.5,
            "width": 0.18,
            "height": 0.12,
            "confidence": 0,
            "source": "fallback",
        }

    verb = "Review" if approval_required else "Move to"
    qualifier = "after approving this one step" if approval_required else "when you are ready"
    instruction = f"{verb} the highlighted target ({target['label']}) {qualifier}."
    if mode == "teach":
        instruction = f"Teach mode: highlighted target is the next safe focus area ({target['label']}); pause after this step."

    return {
        "enabled": True,
        "mode": mode,
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
    clean = re.sub(r"\[operator mode:[^\]]+\]", " ", request.lower())
    terms = []
    for raw in re.findall(r"[a-z0-9]{3,}", clean):
        if raw not in STOP_WORDS and raw not in terms:
            terms.append(raw)
    return terms[:12]


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))
