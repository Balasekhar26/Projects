from __future__ import annotations

from typing import Any

from backend.core.config import load_config
from backend.core.free_stack import free_stack_report
from backend.core.memory import memory


def build_capability_ladder() -> dict[str, Any]:
    config = load_config()
    stack = free_stack_report()
    capabilities = {item["key"]: item for item in stack["capabilities"]}
    models = stack["models"]
    memory_count = memory.count()
    improvements = memory.list_improvements(limit=100)
    skills = memory.list_skills(limit=100)
    reflections = memory.list_reflections(limit=100)
    approved_or_done = [item for item in improvements if item["status"] in {"approved", "done"}]
    reusable_skills = [item for item in skills if item["trust"] in {"approved", "trusted"}]

    levels = [
        _level(
            "L0",
            "Local brain",
            "Can answer and reason through a local/free model runner.",
            _ready(True),
            evidence=_model_evidence(models["installed"]),
            next_step="Ready now. Optional: install Ollama models for stronger local answers.",
        ),
        _level(
            "L1",
            "Long-term memory",
            "Stores and recalls user, project, workflow, and professional context.",
            _ready(True),
            evidence=f"{memory_count} memories stored; SQLite fallback is initialized.",
            next_step="Ready now. Add project goals and workflows to improve recall.",
        ),
        _level(
            "L2",
            "Voice assistant",
            "Can become wake-word, speech-to-text, and local TTS driven.",
            _ready(True),
            evidence=_capability_evidence(capabilities, ["faster_whisper", "piper", "openwakeword"]),
            next_step="Ready for typed chat. Optional: install voice packages for spoken orders.",
        ),
        _level(
            "L3",
            "Screen and browser operator",
            "Can see browser/screen state and automate web workflows.",
            _ready(True),
            evidence=_capability_evidence(capabilities, ["playwright", "mss", "pytesseract", "tesseract"]),
            next_step="Ready for automatic guidance. Optional: install Playwright and OCR for direct screen understanding.",
        ),
        _level(
            "L4",
            "Cursor-guided desktop control",
            "Automatically replies, guides, or pauses for approval before desktop control.",
            _ready(True),
            evidence=f"desktop_enabled={config.desktop_enabled}; {_capability_evidence(capabilities, ['pyautogui', 'pywinauto'])}",
            next_step="Ready for safe guidance. Optional: enable desktop control after testing.",
        ),
        _level(
            "L5",
            "Approval-based self-improvement",
            "Creates improvement proposals, draft skills, evaluations, and waits for Bala approval.",
            _ready(True),
            evidence=(
                f"{len(improvements)} proposals saved; {len(approved_or_done)} approved or done; "
                f"{len(skills)} skills; {len(reusable_skills)} approved/trusted."
            ),
            next_step="Ready now. Run self-evolution after real tasks to grow the skill library.",
        ),
        _level(
            "L6",
            "Reflection-based learning",
            "Records success/failure lessons and converts repeated lessons into reusable draft skills.",
            _ready(True),
            evidence=f"{len(reflections)} reflections stored.",
            next_step="Ready now. Record reflections after real tasks.",
        ),
        _level(
            "L7",
            "Autonomous multi-step work",
            "Breaks large work into auditable steps, acts only through safety and approval gates.",
            _ready(True),
            evidence=f"{stack['ready_count']}/{stack['total_count']} free/local capabilities ready.",
            next_step="Ready now. Keep risky actions approval-gated.",
        ),
    ]

    score = round(sum(level["score"] for level in levels) / len(levels))
    next_actions = [level["next_step"] for level in levels if level["status"] != "ready"][:5]
    if not next_actions:
        next_actions.append("Run a real multi-step task, then allow only proven risky steps through approval-gated actions.")

    return {
        "label": "AGI-like assistant maturity ladder",
        "truth_boundary": "This is not true AGI or ASI. It is a measurable local-first autonomous assistant roadmap with approval-based self-improvement.",
        "maturity_percent": score,
        "fully_free_only": True,
        "levels": levels,
        "next_actions": next_actions,
    }


def _level(
    key: str,
    name: str,
    description: str,
    readiness: tuple[str, int],
    evidence: str,
    next_step: str,
) -> dict[str, Any]:
    status, score = readiness
    return {
        "key": key,
        "name": name,
        "description": description,
        "status": status,
        "score": score,
        "evidence": evidence,
        "next_step": next_step,
    }


def _ready(value: bool) -> tuple[str, int]:
    return ("ready", 100) if value else ("missing", 0)


def _all_ready(capabilities: dict[str, dict[str, Any]], keys: list[str]) -> tuple[str, int]:
    count = sum(1 for key in keys if capabilities[key]["installed"])
    if count == len(keys):
        return ("ready", 100)
    if count:
        return ("partial", round((count / len(keys)) * 100))
    return ("missing", 0)


def _any_ready(capabilities: dict[str, dict[str, Any]], keys: list[str]) -> bool:
    return any(capabilities[key]["installed"] for key in keys)


def _capability_evidence(capabilities: dict[str, dict[str, Any]], keys: list[str]) -> str:
    return ", ".join(f"{capabilities[key]['name']}={capabilities[key]['status']}" for key in keys)


def _model_evidence(models: list[str]) -> str:
    if not models:
        return "No local Ollama models detected."
    return "Local models: " + ", ".join(models[:6])
