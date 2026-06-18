from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.core.config import load_config
from backend.core.free_stack import free_stack_report
from backend.core.memory import memory


CAPABILITY_POINTS = [
    {
        "key": "natural_chat",
        "codex_can": "Understand plain English requests, answer directly when no tool is needed, and stay concise.",
        "kattappa_equivalent": "Chat endpoint, WebSocket chat, evaluator fallback, and compact desktop replies.",
        "files": ["backend/main.py", "backend/agents/evaluator.py", "apps/desktop/src/components/ChatPanel.tsx"],
        "next_move": "Keep replies short by default and expand only when the user asks.",
    },
    {
        "key": "task_routing",
        "codex_can": "Decide whether a request needs code, tools, desktop action, research, or only a reply.",
        "kattappa_equivalent": "Planner routes every message through specialist agents and the safety node.",
        "files": ["backend/agents/planner.py", "backend/core/graph.py", "backend/agents/safety_agent.py"],
        "next_move": "Add route examples whenever a real user task is misclassified.",
    },
    {
        "key": "long_context_memory",
        "codex_can": "Use prior conversation and project context while working.",
        "kattappa_equivalent": "SQLite chat sessions plus Chroma memory context and related-message recall.",
        "files": ["backend/core/memory.py", "backend/agents/memory_agent.py"],
        "metric": "memory",
        "next_move": "Summarize older runs into durable project memories after approval.",
    },
    {
        "key": "project_file_awareness",
        "codex_can": "Read a codebase, identify relevant files, and avoid unrelated changes.",
        "kattappa_equivalent": "Project indexer, builder workspace map, and local builder profile.",
        "files": ["backend/core/project_indexer.py", "backend/core/builder_brain.py"],
        "next_move": "Cache per-project architecture briefs so repeated tasks start faster.",
    },
    {
        "key": "coding_loop",
        "codex_can": "Plan edits, patch files, run focused verification, and iterate on failures.",
        "kattappa_equivalent": "Coder agent, builder protocol, local review helper, GSD workflow generator, and test-aware task resume.",
        "files": [
            "backend/agents/coder.py",
            "backend/core/builder_brain.py",
            "backend/tools/local_creator_tools.py",
            "backend/core/task_resume.py",
        ],
        "next_move": "Add a real patch executor only behind approval, with diff preview before file writes.",
    },
    {
        "key": "terminal_and_builds",
        "codex_can": "Run shell commands, builds, tests, and report important output.",
        "kattappa_equivalent": "Terminal tool with allowlist/risk handling plus launcher and setup scripts.",
        "files": ["backend/tools/terminal_tools.py", "scripts/run.cmd", "installer/setup_kattappa.py"],
        "next_move": "Store verified commands per project so Kattappa can pick the right smoke test automatically.",
    },
    {
        "key": "browser_and_web",
        "codex_can": "Inspect websites or local web apps when a task needs live browser context.",
        "kattappa_equivalent": "Browser agent and Playwright-backed browser tool with graceful fallback.",
        "files": ["backend/agents/browser.py", "backend/tools/browser_tools.py"],
        "capability_keys": ["playwright"],
        "next_move": "Add screenshot verification summaries for local UI changes after approval.",
    },
    {
        "key": "desktop_operator",
        "codex_can": "Guide or operate the desktop cautiously with user approval.",
        "kattappa_equivalent": "Desktop agent, operator plan, cursor guidance overlay, and approval continuation.",
        "files": [
            "backend/agents/desktop.py",
            "backend/core/operator.py",
            "backend/core/approval_continuation.py",
            "apps/desktop/src/components/DesktopGuidanceOverlay.tsx",
        ],
        "next_move": "Keep direct control disabled by default; promote only repeatable, approved actions.",
    },
    {
        "key": "screen_vision",
        "codex_can": "Use screenshots and visual context when available.",
        "kattappa_equivalent": "Screen tools, OCR words, vision agent, and macOS permission-gated capture.",
        "files": ["backend/tools/screen_tools.py", "backend/agents/vision.py", "backend/config.yaml"],
        "capability_keys": ["mss", "pytesseract", "tesseract"],
        "next_move": "Use screen capture only after setup/preflight and explicit screen-related tasks.",
    },
    {
        "key": "voice_assistant",
        "codex_can": "Handle spoken commands when a voice path exists.",
        "kattappa_equivalent": "Offline Kattappa voice profile with openWakeWord, local STT, and local/native TTS fallbacks.",
        "files": ["backend/tools/voice_tools.py", "backend/agents/voice.py", "apps/desktop/src/components/ChatPanel.tsx"],
        "capability_keys": ["faster_whisper", "openwakeword", "piper"],
        "next_move": "Add a push-to-talk fallback when microphone capture is blocked by the desktop runtime.",
    },
    {
        "key": "approvals_and_safety",
        "codex_can": "Pause before risky actions and resume work after approval.",
        "kattappa_equivalent": "Approval records, continuation endpoint, safety agent, and desktop approval loop.",
        "files": ["backend/core/approval_continuation.py", "backend/agents/safety_agent.py", "backend/main.py"],
        "next_move": "Show one-line risk reasons for each approval so the user can decide faster.",
    },
    {
        "key": "visible_queue",
        "codex_can": "Show active work, status, and queued user messages.",
        "kattappa_equivalent": "Desktop queue strip, current task state, compact status, and queued turn handling.",
        "files": ["apps/desktop/src/App.tsx", "apps/desktop/src/components/ChatPanel.tsx", "apps/desktop/src/styles.css"],
        "next_move": "Persist queued tasks across app restarts if a long task is still active.",
    },
    {
        "key": "long_tasks",
        "codex_can": "Resume work from saved task state and checkpoints.",
        "kattappa_equivalent": "Long-task table, resume planner, and task panel.",
        "files": ["backend/core/task_resume.py", "backend/core/memory.py", "apps/desktop/src/components/PanelContent.tsx"],
        "next_move": "Auto-create a long task for work that runs past one chat turn.",
    },
    {
        "key": "tool_scouting",
        "codex_can": "Identify useful libraries/tools and prefer official/free sources when adding capability.",
        "kattappa_equivalent": "Fully-free tool scout, source-first policy, and approval-gated tool adoption.",
        "files": ["backend/core/tool_scout.py", "backend/core/source_policy.py", "backend/core/tool_adoption.py"],
        "next_move": "Record blocked paid tools and their free replacements per project.",
    },
    {
        "key": "self_improvement",
        "codex_can": "Reflect on failures and improve workflows over time.",
        "kattappa_equivalent": "Self-improver, reflections, skill library, skill evaluations, and approval-gated evolution.",
        "files": ["backend/agents/self_improver.py", "backend/core/self_evolution.py", "backend/core/memory.py"],
        "next_move": "Convert repeated successful routes into trusted skills after review.",
    },
    {
        "key": "multi_system_handoff",
        "codex_can": "Delegate suitable work when another worker/runtime is better equipped.",
        "kattappa_equivalent": "Paired local worker runtime with privacy contract and cleanup receipt.",
        "files": ["backend/core/cluster_runtime.py", "backend/core/cluster_plan.py"],
        "next_move": "Expose paired-node health and cleanup receipts in the desktop UI.",
    },
    {
        "key": "setup_and_packaging",
        "codex_can": "Make projects easier to install, run, and verify locally.",
        "kattappa_equivalent": "Individual setup/run launchers, native Tauri bundle, shortcut creation, and macOS quiet startup.",
        "files": ["installer/setup_kattappa.py", "apps/desktop/src-tauri/src/lib.rs", "README.md"],
        "next_move": "Add one-click repair for missing optional dependencies from the desktop app.",
    },
    {
        "key": "documents_and_creator_tools",
        "codex_can": "Create useful docs, outlines, diagrams, reviews, and structured content.",
        "kattappa_equivalent": "Local creator tools for deck outlines, Mermaid diagrams, context compression, code review, GSD workflows, markdown conversion, and marketing kits.",
        "files": ["backend/tools/local_creator_tools.py", "backend/main.py"],
        "next_move": "Add editable file export for generated Markdown, diagrams, and reports after approval.",
    },
]


def codex_parity_report() -> dict[str, Any]:
    config = load_config()
    root = config.root
    stack = free_stack_report()
    capabilities = {item["key"]: item for item in stack["capabilities"]}
    items = [_item_status(root, capabilities, point) for point in CAPABILITY_POINTS]
    score = round(sum(item["score"] for item in items) / len(items))
    gaps = [item for item in items if item["status"] != "ready"]
    next_builds = [item["next_move"] for item in sorted(items, key=lambda item: item["score"])[:6]]
    return {
        "name": "Codex Rival Capability Map",
        "truth_boundary": (
            "Kattappa is not OpenAI Codex and does not use private OpenAI runtime abilities. "
            "This map builds local/free equivalents for the same assistant workflow points."
        ),
        "parity_percent": score,
        "fully_free_only": True,
        "local_first": True,
        "memory_count": memory.count(),
        "items": items,
        "strongest_gaps": gaps[:5],
        "next_builds": list(dict.fromkeys(next_builds)),
        "user_order_contract": [
            "Take one plain order by text or voice.",
            "Answer directly when no action is needed.",
            "Route tool work to the right specialist agent.",
            "Show current processing and queued work.",
            "Ask approval before risky actions, then continue automatically after approval.",
            "Remember useful context locally and improve through approved skills.",
        ],
    }


def codex_parity_answer(limit: int = 18) -> str:
    report = codex_parity_report()
    lines = [
        f"{item['codex_can']} -> Kattappa: {item['kattappa_equivalent']} ({item['status_label']})."
        for item in report["items"][:limit]
    ]
    next_lines = "\n".join(f"- {step}" for step in report["next_builds"][:5])
    return (
        f"{report['name']}: {report['parity_percent']}% local/free workflow parity.\n"
        f"{report['truth_boundary']}\n\n"
        "What I can do, and Kattappa's matching point:\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\n\nNext build targets:\n"
        + next_lines
    )


def _item_status(
    root: Path,
    capabilities: dict[str, dict[str, Any]],
    point: dict[str, Any],
) -> dict[str, Any]:
    files = point.get("files", [])
    existing = [path for path in files if (root / path).exists()]
    file_score = round((len(existing) / len(files)) * 70) if files else 70
    capability_keys = point.get("capability_keys", [])
    capability_score = 30
    if capability_keys:
        installed = [
            key
            for key in capability_keys
            if capabilities.get(key, {}).get("installed")
        ]
        capability_score = round((len(installed) / len(capability_keys)) * 30)
    metric_bonus = 0
    if point.get("metric") == "memory" and memory.count() > 0:
        metric_bonus = 15
    score = max(0, min(100, file_score + capability_score + metric_bonus))
    if score >= 85:
        status = "ready"
    elif score >= 55:
        status = "partial"
    else:
        status = "fallback"
    return {
        "key": point["key"],
        "codex_can": point["codex_can"],
        "kattappa_equivalent": point["kattappa_equivalent"],
        "status": status,
        "status_label": _status_label(status),
        "score": score,
        "evidence": f"{len(existing)}/{len(files)} local implementation files present",
        "files": files,
        "next_move": point["next_move"],
        "free_local_rule": "Core path must remain fully free, local-first, and approval-gated for risky work.",
    }


def _status_label(status: str) -> str:
    if status == "ready":
        return "ready"
    if status == "partial":
        return "partly built with safe fallback"
    return "fallback only"
