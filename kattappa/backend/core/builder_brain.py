from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from backend.core.codex_parity import codex_parity_answer, codex_parity_report
from backend.core.config import load_config
from backend.core.source_policy import source_first_policy


LOCAL_ANALYTICS_PROJECTS = [
    ("kattappa", "Kattappa AI OS Assistant"),
    ("pcb-doctor", "PCB Doctor"),
    ("ai-cyber-shield", "AI Cyber Shield"),
    ("universal-translator", "Universal Translator / ULT"),
    ("musical-keyboard", "Musical Keyboard"),
    ("dews", "DEWS / Defensive Early Warning System"),
    ("07-NeuroSeed", "NeuroSeed"),
]

REFERENCE_REPLACEMENTS = [
    {
        "source": "Paxel-style AI coding analytics",
        "not_added_reason": "The public Paxel flow is free, but it summarizes selected transcript excerpts through hosted models and uploads a report payload.",
        "fully_free_replacement": "Kattappa Local Builder Profile",
        "added_to": "Kattappa backend and desktop Agents panel",
        "why_it_improves_products": "Scores planning, execution, engineering quality, product instinct, and steering from local repo signals so every project gets a private improvement compass.",
    },
    {
        "source": "OpenRouter/Gemini/ElevenLabs-style assistant routing",
        "not_added_reason": "Free tiers and cloud APIs are not stable fully free/local core dependencies.",
        "fully_free_replacement": "Ollama + faster-whisper/openWakeWord + Piper/pyttsx3/native fallback",
        "added_to": "Kattappa local assistant stack",
        "why_it_improves_products": "Keeps voice, planning, memory, and computer-control workflows runnable without paid API keys.",
    },
    {
        "source": "MARK-style file, screen, memory, automation, and desktop control patterns",
        "not_added_reason": "Useful pattern, but external repo code is not copied into the core.",
        "fully_free_replacement": "Kattappa owned adapters for files, screen/OCR, memory, browser, terminal, desktop, voice, and approvals",
        "added_to": "Kattappa Builder Brain tracking",
        "why_it_improves_products": "Confirms which local assistant capabilities already exist and highlights missing polish without creating a hard dependency on another project.",
    },
]

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
    "Safety-aware automatic desktop action routing",
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
        "local_builder_analytics": local_builder_analytics(),
        "codex_parity": codex_parity_report(),
        "free_replacements_from_references": REFERENCE_REPLACEMENTS,
        "approval_required_for": [
            "file writes",
            "package installs",
            "destructive commands",
            "desktop control actions",
            "security, credentials, payments, or data deletion",
        ],
        "source_first": source_first_policy(),
    }


def local_builder_analytics() -> dict[str, Any]:
    config = load_config()
    repo_root = config.root.parent
    projects = [_project_build_signal(repo_root, project_id, name) for project_id, name in LOCAL_ANALYTICS_PROJECTS]
    changed_files = _git_lines(repo_root, ["status", "--short"])
    recent_commits = _git_lines(repo_root, ["log", "--since=30 days ago", "--pretty=%H"])
    dimension_scores = _builder_dimension_scores(projects, changed_files, recent_commits)
    growth_edges = _growth_edges(dimension_scores, projects)
    return {
        "mode": "fully_free_local_builder_profile",
        "cost": "free",
        "privacy_boundary": (
            "No code, .env files, raw chat transcripts, or AI-agent sessions are uploaded. "
            "This report is computed from local repository structure and git metadata only."
        ),
        "inspired_by": [
            "Paxel builder-profile dimensions",
            "MARK-style local assistant capability map",
        ],
        "blocked_core_dependencies": [
            "hosted transcript analytics",
            "paid or quota-limited LLM APIs",
            "closed voice services",
            "copied external assistant code",
        ],
        "archetype": _builder_archetype(dimension_scores),
        "dimensions": dimension_scores,
        "growth_edges": growth_edges,
        "repo_activity": {
            "changed_files": len(changed_files),
            "recent_commits_30d": len(recent_commits),
            "has_dirty_worktree": bool(changed_files),
        },
        "projects": projects,
        "free_replacements": REFERENCE_REPLACEMENTS,
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
    lower = user_request.lower()
    if any(term in lower for term in ("rival", "codex", "what can you do", "list out what can")):
        return codex_parity_answer()
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
        ("backend/core/operator.py", "Automatic reply, guidance, and approval-gated desktop action policy"),
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


def _project_build_signal(repo_root: Path, project_id: str, name: str) -> dict[str, Any]:
    path = repo_root / project_id
    if not path.exists():
        return {
            "id": project_id,
            "name": name,
            "path": str(path),
            "exists": False,
            "files_scanned": 0,
            "signals": {},
            "strengths": [],
            "next_local_moves": ["Create or restore the project folder before adding features."],
        }
    files = _collect_project_files(path, limit=500)
    roles = Counter(_guess_role(file.relative_to(path)) for file in files)
    extensions = Counter(file.suffix.lower() or "<none>" for file in files)
    signals = {
        "docs": sum(1 for file in files if file.suffix.lower() in {".md", ".txt"}),
        "tests": sum(1 for file in files if "test" in file.name.lower() or "tests" in file.parts),
        "launchers": sum(1 for file in files if file.suffix.lower() in {".bat", ".cmd", ".ps1", ".sh", ".vbs"} or file.name.lower() in {"package.json", "pyproject.toml"}),
        "backend_files": sum(1 for file in files if "backend" in file.parts or file.suffix.lower() == ".py"),
        "desktop_or_ui_files": sum(1 for file in files if "desktop" in file.parts or file.suffix.lower() in {".tsx", ".ts", ".jsx", ".js", ".css", ".html"}),
        "memory_or_data_files": sum(1 for file in files if any(part in {"memory", "data", "models"} for part in file.parts)),
    }
    return {
        "id": project_id,
        "name": name,
        "path": str(path),
        "exists": True,
        "files_scanned": len(files),
        "signals": signals,
        "top_roles": [{"name": key, "count": value} for key, value in roles.most_common(5)],
        "top_extensions": [{"name": key, "count": value} for key, value in extensions.most_common(5)],
        "strengths": _project_strengths(signals),
        "next_local_moves": _project_next_moves(project_id, signals),
    }


def _collect_project_files(root: Path, limit: int = 500) -> list[Path]:
    ignored_parts = {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        "target",
        "dist",
        "build",
        ".ult-runtime",
        "runtime",
    }
    files: list[Path] = []
    for path in root.rglob("*"):
        if len(files) >= limit:
            break
        if any(part in ignored_parts for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def _builder_dimension_scores(
    projects: list[dict[str, Any]],
    changed_files: list[str],
    recent_commits: list[str],
) -> list[dict[str, Any]]:
    present_projects = [project for project in projects if project["exists"]]
    docs = sum(project["signals"].get("docs", 0) for project in present_projects)
    tests = sum(project["signals"].get("tests", 0) for project in present_projects)
    launchers = sum(project["signals"].get("launchers", 0) for project in present_projects)
    ui_files = sum(project["signals"].get("desktop_or_ui_files", 0) for project in present_projects)
    backend_files = sum(project["signals"].get("backend_files", 0) for project in present_projects)
    dirty_projects = {line.split(maxsplit=1)[-1].split("/", 1)[0] for line in changed_files if line.strip()}
    dimensions = [
        (
            "planning",
            _score(docs * 3 + launchers * 2 + len(present_projects) * 4, 100),
            f"{docs} docs and {launchers} launch/config entrypoints found across {len(present_projects)} projects.",
        ),
        (
            "execution",
            _score(len(recent_commits) * 8 + len(changed_files) * 3 + len(dirty_projects) * 6, 100),
            f"{len(recent_commits)} commits in 30 days and {len(changed_files)} changed files currently visible in git.",
        ),
        (
            "engineering_quality",
            _score(tests * 5 + backend_files // 2 + launchers * 3, 100),
            f"{tests} test files/signals and {backend_files} backend/code files scanned.",
        ),
        (
            "product_instinct",
            _score(ui_files // 2 + docs * 2 + len(present_projects) * 5, 100),
            f"{ui_files} UI/app files plus product docs across the project set.",
        ),
        (
            "steering",
            _score(len(dirty_projects) * 8 + tests * 2 + docs, 100),
            f"Current work spans {len(dirty_projects)} project folder(s), with tests/docs used as steering anchors.",
        ),
    ]
    return [
        {
            "key": key,
            "label": key.replace("_", " ").title(),
            "score": score,
            "evidence": evidence,
        }
        for key, score, evidence in dimensions
    ]


def _growth_edges(dimensions: list[dict[str, Any]], projects: list[dict[str, Any]]) -> list[str]:
    edges = []
    lowest = sorted(dimensions, key=lambda item: item["score"])[:2]
    for item in lowest:
        if item["key"] == "engineering_quality":
            edges.append("Add one focused smoke test or compile check per product launcher before adding bigger features.")
        elif item["key"] == "execution":
            edges.append("Keep small verified commits or task checkpoints so product progress is easier to resume.")
        elif item["key"] == "planning":
            edges.append("Turn each imported idea into a short local plan: free replacement, touched files, verification command.")
        elif item["key"] == "product_instinct":
            edges.append("Expose one useful status panel per product so users can see readiness without reading logs.")
        elif item["key"] == "steering":
            edges.append("Prefer one active product change at a time unless a shared safety rule is being updated.")
    for project in projects:
        if project["exists"] and project["signals"].get("tests", 0) == 0:
            edges.append(f"{project['name']}: add a tiny local smoke test or validation script.")
            break
    return list(dict.fromkeys(edges))[:5]


def _builder_archetype(dimensions: list[dict[str, Any]]) -> str:
    scores = {item["key"]: item["score"] for item in dimensions}
    if scores.get("engineering_quality", 0) >= 70 and scores.get("planning", 0) >= 70:
        return "Local Quality Architect"
    if scores.get("execution", 0) >= 70:
        return "Velocity Builder"
    if scores.get("product_instinct", 0) >= 70:
        return "Product Systems Builder"
    return "Local-First Builder"


def _project_strengths(signals: dict[str, int]) -> list[str]:
    strengths = []
    if signals.get("docs", 0):
        strengths.append("documented")
    if signals.get("tests", 0):
        strengths.append("has local verification")
    if signals.get("launchers", 0):
        strengths.append("has launch/setup entrypoints")
    if signals.get("backend_files", 0):
        strengths.append("has backend/logic surface")
    if signals.get("desktop_or_ui_files", 0):
        strengths.append("has UI/application surface")
    return strengths or ["needs first readiness signals"]


def _project_next_moves(project_id: str, signals: dict[str, int]) -> list[str]:
    moves = []
    if signals.get("tests", 0) == 0:
        moves.append("Add a local smoke test or syntax-check script.")
    if signals.get("docs", 0) == 0:
        moves.append("Add a short README with purpose, run command, and safety boundary.")
    if signals.get("launchers", 0) == 0:
        moves.append("Add an individual run/setup entrypoint so the project works alone.")
    if project_id == "kattappa":
        moves.append("Keep assistant analytics local and approval-gated before adopting new tools.")
    return moves[:3] or ["Keep polishing with focused, verified changes."]


def _score(value: int, ceiling: int) -> int:
    return max(0, min(100, round((value / ceiling) * 100)))


def _git_lines(cwd: Path, args: list[str]) -> list[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


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
