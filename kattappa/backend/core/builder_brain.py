from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.core.config import load_config
from backend.core.source_policy import source_first_policy


BUILDER_PROTOCOL = [
    {
        "name": "Manager worker routes the task",
        "description": "Take the user's chat request, understand intent/risk, then assign the work to the best specialist worker.",
    },
    {
        "name": "Understand the request",
        "description": "Restate the goal, detect risk, and decide whether the work needs code, tools, or only an answer.",
    },
    {
        "name": "Search for fully free helpers",
        "description": "When a task needs a new capability, scout the internet and local catalog for fully free/open-source/local-first tools or technologies.",
    },
    {
        "name": "Read before editing",
        "description": "Inspect relevant files, tests, config, launch scripts, and existing patterns before changing anything.",
    },
    {
        "name": "Plan small safe changes",
        "description": "Prefer narrow edits that fit the current architecture instead of large rewrites.",
    },
    {
        "name": "Patch deliberately",
        "description": "Use patch-style edits, keep unrelated files untouched, and preserve user changes.",
    },
    {
        "name": "Verify",
        "description": "Run focused tests/builds, capture failures, fix the real cause, and report what was verified.",
    },
    {
        "name": "Approval gate",
        "description": "Ask Bala before destructive actions, installs, credentials, unsafe desktop control, or risky system changes.",
    },
    {
        "name": "Source-first dependency rule",
        "description": "Build core agents/APIs locally, inspect free/open-source tools before install, and keep downloaded tools as replaceable adapters.",
    },
    {
        "name": "Build own tools from learned patterns",
        "description": "Use external tools as references only after license/source inspection, then rebuild useful behavior in Kattappa AI OS style where practical.",
    },
    {
        "name": "Remember and improve",
        "description": "Use the improvement worker to record reflections, propose reusable skills/tools, and promote them only after approval/trust.",
    },
]


BUILDER_CAPABILITIES = [
    "Manager worker for chat-to-task assignment",
    "Specialist worker graph for coding, browser, desktop, files, terminal, vision, voice, research, finance, memory, safety, and evaluation",
    "Improvement worker for continuous self-evolution proposals",
    "Fully-free tool scouting before adding new capabilities",
    "Repository map and file role awareness",
    "Coding-agent style plan -> patch -> test loop",
    "Approval-based self-improvement proposals",
    "Skill/reflection/evaluation memory",
    "Launch/debug workflow awareness",
    "Local-first model routing and fallback",
    "Safety-aware desktop/operator mode control",
]


KATTAPPA_MOTIVE = (
    "Kattappa AI OS Assistant is meant to be Bala's personal and professional assistant for the installed system. "
    "It should understand chat input, let a manager worker assign tasks to expert workers, use only fully free/local-first "
    "tools as core dependencies, scout the internet for better free/open-source technologies when a task needs them, "
    "support external tools that can run locally or in the cloud when they are fully free and adapter-gated, "
    "and continuously improve itself through an approval-gated improvement worker."
)


WORKER_MODEL = {
    "manager_worker": {
        "role": "Reads the chat box request, detects risk, selects the right specialist worker, and keeps approvals visible.",
        "backend": "backend.core.graph + backend.agents.planner",
    },
    "specialist_workers": {
        "role": "Each worker handles one kind of task deeply: coding, browser, desktop, files, terminal, vision, voice, research, finance, memory, safety, builder, evaluator.",
        "backend": "backend.agents.*",
    },
    "improvement_worker": {
        "role": "Continuously proposes safe improvements, reusable skills, and new local tools after tasks and reflections.",
        "backend": "backend.agents.self_improver + backend.core.self_evolution",
    },
    "tool_scout_worker": {
        "role": "Searches for fully free/open-source/local-first tools and converts useful ideas into approval-gated build-own or adapter proposals.",
        "backend": "backend.core.tool_scout",
    },
}


def builder_profile() -> dict[str, Any]:
    config = load_config()
    return {
        "name": "Kattappa Builder Brain",
        "truth_boundary": (
            "This is not OpenAI private code or a copy of Codex internals. "
            "It is a local implementation of the engineering workflow Bala wants inside Kattappa AI OS."
        ),
        "workspace": str(config.root),
        "motive": KATTAPPA_MOTIVE,
        "worker_model": WORKER_MODEL,
        "protocol": BUILDER_PROTOCOL,
        "capabilities": BUILDER_CAPABILITIES,
        "approval_required_for": [
            "file writes",
            "package installs",
            "destructive commands",
            "desktop assist/autonomous actions",
            "security, credentials, payments, or data deletion",
        ],
        "source_first": source_first_policy(),
    }


def workspace_map(limit: int = 80) -> dict[str, Any]:
    config = load_config()
    root = config.root
    files = []
    ignored_parts = {"node_modules", ".git", "__pycache__", "target", "dist", ".venv"}
    for path in root.rglob("*"):
        if len(files) >= limit:
            break
        if any(part in ignored_parts for part in path.parts):
            continue
        if path.is_file():
            files.append(_file_info(root, path))
    return {
        "root": str(root),
        "files_shown": len(files),
        "limit": limit,
        "files": files,
        "main_systems": _main_systems(root),
    }


def builder_answer(user_request: str) -> str:
    profile = builder_profile()
    systems = workspace_map(limit=30)["main_systems"]
    protocol_lines = "\n".join(f"- {item['name']}: {item['description']}" for item in profile["protocol"])
    systems_lines = "\n".join(f"- {item['path']}: {item['role']}" for item in systems)
    return (
        "I have added a local Builder Brain concept into Kattappa AI OS.\n\n"
        "What it knows how to do:\n"
        f"{protocol_lines}\n\n"
        "Important boundary:\n"
        f"{profile['truth_boundary']}\n\n"
        "Main local systems it can reason about:\n"
        f"{systems_lines}\n\n"
        "Use it by asking things like:\n"
        "- analyze this project\n"
        "- what files control launch?\n"
        "- propose a safe code change\n"
        "- create a self-improvement skill\n"
        "- explain your builder workflow"
    )


def _main_systems(root: Path) -> list[dict[str, str]]:
    candidates = [
        ("backend/main.py", "FastAPI API, WebSocket chat, health/ready endpoints"),
        ("backend/core/graph.py", "LangGraph agent routing and execution"),
        ("backend/core/memory.py", "SQLite + Chroma memory, approvals, skills, reflections"),
        ("backend/core/operator.py", "Observe/guide/assist/autonomous operator modes"),
        ("backend/core/model_router.py", "Ollama local model selection and fallback"),
        ("backend/core/builder_brain.py", "Local engineering workflow knowledge"),
        ("apps/desktop/src/App.tsx", "ChatGPT-like desktop interface"),
        ("apps/desktop/src/styles.css", "Desktop interface styling and launch animation"),
        ("setup.bat", "First-run Windows setup launcher"),
        ("run.exe", "Supported Windows app and service launcher"),
    ]
    return [
        {"path": path, "role": role, "exists": str((root / path).exists())}
        for path, role in candidates
    ]


def _file_info(root: Path, path: Path) -> dict[str, Any]:
    rel = path.relative_to(root)
    return {
        "path": str(rel),
        "size": path.stat().st_size,
        "role": _guess_role(rel),
    }


def _guess_role(path: Path) -> str:
    text = str(path).replace("\\", "/").lower()
    if text.endswith(".bat") or text.endswith(".vbs") or text.endswith(".ps1"):
        return "launcher/script"
    if "backend/core" in text:
        return "backend core"
    if "backend/agents" in text:
        return "agent"
    if "backend/tools" in text:
        return "tool"
    if "apps/desktop/src" in text:
        return "desktop ui"
    if "tests" in text:
        return "test"
    if text.endswith((".md", ".txt")):
        return "documentation"
    return "project file"
