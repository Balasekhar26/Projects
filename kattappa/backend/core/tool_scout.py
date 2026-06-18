from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import httpx

from backend.core.memory import memory


@dataclass(frozen=True)
class ToolCandidate:
    capability: str
    tool: str
    source: str
    license_note: str
    best_for: tuple[str, ...]
    build_own_plan: str


CATALOG = [
    ToolCandidate(
        capability="coding agent sandbox",
        tool="OpenHands-inspired local coding loop",
        source="https://github.com/OpenHands/OpenHands",
        license_note="Inspect upstream license before reuse. Prefer rebuilding the workflow: plan, edit, test, reflect.",
        best_for=("code", "bug", "test", "build", "repo", "project", "fix"),
        build_own_plan=(
            "Build our own local coding loop: index files, create patch plan, edit through approved tools, "
            "run tests, summarize diff, and record reflection. Use OpenHands only as an architecture reference."
        ),
    ),
    ToolCandidate(
        capability="repo architecture prompt export",
        tool="Local repo-to-prompt exporter",
        source="local implementation inspired by repo summarization patterns",
        license_note=(
            "Build locally from our own file index and ignore rules. Do not depend on external GitReverse-style "
            "services for private or project code."
        ),
        best_for=("repo prompt", "gitreverse", "reverse repo", "architecture prompt", "summarize repo"),
        build_own_plan=(
            "Use rg/git metadata to list files, apply .gitignore and size filters, summarize README/package/config "
            "files first, then emit an AI-readable architecture brief with no network dependency."
        ),
    ),
    ToolCandidate(
        capability="git safety workflow",
        tool="Git CLI + GitHub Desktop guidance",
        source="local git plus https://github.com/desktop/desktop",
        license_note=(
            "Git and GitHub Desktop are free/open-source tools. Keep destructive commands approval-gated "
            "and prefer restore/revert/status/diff workflows for shared projects."
        ),
        best_for=("git", "reverse", "revert", "reset", "restore", "commit", "branch", "github desktop"),
        build_own_plan=(
            "Build a local Git safety helper that checks status first, explains restore vs revert vs reset, "
            "blocks destructive reset unless explicitly approved, and suggests GitHub Desktop for visual review."
        ),
    ),
    ToolCandidate(
        capability="durable long-running agent workflow",
        tool="LangGraph-style checkpointed graph",
        source="https://docs.langchain.com/oss/python/langgraph/durable-execution",
        license_note="Already used as a replaceable workflow adapter. Keep Kattappa-specific nodes in our code.",
        best_for=("long task", "resume", "agent", "workflow", "approval", "autonomous"),
        build_own_plan=(
            "Keep the graph local, store every step in SQLite, add pause/resume checkpoints, and require approval "
            "before risky actions."
        ),
    ),
    ToolCandidate(
        capability="local model runtime",
        tool="Ollama / llama.cpp adapter",
        source="https://github.com/ollama/ollama",
        license_note="Model weights are not normal code. Keep local model profiles swappable and removable.",
        best_for=("model", "llm", "answer", "chat", "reason", "offline"),
        build_own_plan=(
            "Do not rebuild model training. Build our own router, timeout fallback, model health checks, and local "
            "profile manager around free local runtimes."
        ),
    ),
    ToolCandidate(
        capability="multi-system local AI cluster",
        tool="exo for inference + Ray for worker orchestration",
        source="https://github.com/exo-explore/exo and https://docs.ray.io/",
        license_note=(
            "Use only on trusted local systems. exo and Ray are free/open options; avoid crypto reward networks "
            "and do not expose cluster APIs to the public internet."
        ),
        best_for=("cluster", "multiple systems", "multi system", "distributed", "hyperspace", "pods", "workers"),
        build_own_plan=(
            "Add a cluster adapter boundary: exo handles local multi-machine model inference, Ray handles "
            "background workers such as indexing, research, simulation, tests, and project scans. Keep a single "
            "Kattappa AI OS manager node with approval gates for actions on other machines."
        ),
    ),
    ToolCandidate(
        capability="browser automation",
        tool="Playwright adapter",
        source="https://github.com/microsoft/playwright",
        license_note="Use as replaceable browser adapter; do not make it the agent brain.",
        best_for=("browser", "website", "web", "click", "form", "search"),
        build_own_plan=(
            "Build our own browser-agent policy: observe page, propose action, approval gate, execute one step, "
            "record result. Keep Playwright as the browser driver only."
        ),
    ),
    ToolCandidate(
        capability="semantic local memory",
        tool="ChromaDB/Qdrant-style vector memory",
        source="https://github.com/chroma-core/chroma",
        license_note="Use as replaceable vector store; store canonical task/chat state in SQLite first.",
        best_for=("memory", "remember", "history", "recall", "knowledge"),
        build_own_plan=(
            "Keep SQLite as source of truth, add vector search adapters, and build our own memory ranking rules "
            "for chats, projects, approvals, and long tasks."
        ),
    ),
    ToolCandidate(
        capability="one-file backend",
        tool="SQLite default with optional PocketBase adapter",
        source="https://pocketbase.io/",
        license_note=(
            "PocketBase is an MIT one-file backend candidate. Keep SQLite as the default source of truth and "
            "enable PocketBase only after approval when realtime/auth/files are truly needed."
        ),
        best_for=("supabase", "firebase", "backend", "auth", "realtime", "database", "files"),
        build_own_plan=(
            "Use the existing SQLite project state first. If a project needs realtime/auth/file APIs, add a "
            "PocketBase adapter boundary without replacing the one setup file or one run executable rule."
        ),
    ),
    ToolCandidate(
        capability="local product analytics",
        tool="SQLite event, error, funnel, and feature-usage logs",
        source="local implementation inspired by PostHog-style product analytics",
        license_note=(
            "Do not send telemetry to cloud services. Store local product events in SQLite and expose summaries "
            "only to the local improvement agent."
        ),
        best_for=("posthog", "analytics", "session replay", "feature flag", "usage", "funnel", "tracking"),
        build_own_plan=(
            "Build a local analytics table for events, errors, feature flags, and funnels. Summarize counts for "
            "self-improvement proposals without recording private chat content."
        ),
    ),
    ToolCandidate(
        capability="local deck generator",
        tool="Kattappa Markdown deck outline generator",
        source="local implementation inspired by Pitch/Gamma presentation workflows",
        license_note=(
            "Pitch and Gamma are freemium/account tools. Keep the core free by generating Markdown deck "
            "outlines locally; export through Markdown, Marp, Reveal.js, or manual PPT conversion."
        ),
        best_for=("pitch", "gamma", "deck", "presentation", "slides", "investor", "demo"),
        build_own_plan=(
            "Use backend.tools.local_creator_tools.create_local_deck_outline to create project pitch/demo "
            "slides with local templates and no cloud upload."
        ),
    ),
    ToolCandidate(
        capability="local diagram generator",
        tool="Kattappa Mermaid diagram generator",
        source="local implementation inspired by Napkin AI text-to-visual workflows",
        license_note=(
            "Napkin is freemium/credit-based. Generate Mermaid locally and render through free Mermaid-compatible tools."
        ),
        best_for=("napkin", "diagram", "flowchart", "mind map", "architecture", "visual", "mermaid"),
        build_own_plan=(
            "Use backend.tools.local_creator_tools.create_mermaid_diagram to turn text into flowcharts or "
            "mind maps for architecture docs, PCB repair flows, DEWS incidents, and NeuroSeed learning maps."
        ),
    ),
    ToolCandidate(
        capability="local context compression",
        tool="Kattappa deterministic context compressor",
        source="local implementation inspired by Headroom context compression",
        license_note=(
            "Headroom is open-source, but Kattappa has a tiny built-in compressor first. Consider Headroom only "
            "as an optional adapter after license/source review."
        ),
        best_for=("headroom", "compress", "context", "token", "logs", "tool output", "long file"),
        build_own_plan=(
            "Use backend.tools.local_creator_tools.compress_context to preserve high-signal lines from logs, "
            "tool output, and notes before adding them to local model context."
        ),
    ),
    ToolCandidate(
        capability="local code review",
        tool="Kattappa heuristic diff reviewer",
        source="local implementation inspired by CodeRabbit PR review workflows",
        license_note=(
            "CodeRabbit is a hosted review product with pricing tiers. Keep core review local with deterministic "
            "checks; optional external review must be explicitly approved and must not receive private code."
        ),
        best_for=(
            "coderabbit",
            "code review",
            "pr review",
            "review diff",
            "security issue",
            "bug review",
        ),
        build_own_plan=(
            "Use backend.tools.local_creator_tools.local_code_review to scan diffs for secrets, unsafe shell, "
            "debug leftovers, broad exceptions, TODO/FIXME markers, and simple SQL injection patterns."
        ),
    ),
    ToolCandidate(
        capability="local coding assistant",
        tool="Kattappa project index + review + GSD workflow",
        source="local implementation inspired by Blackbox AI coding-assistant workflows",
        license_note=(
            "Blackbox AI is a hosted/freemium coding assistant. Keep Kattappa's core code help local through "
            "project indexing, deterministic review, repo prompt export, and plan-execute-verify-fix loops."
        ),
        best_for=(
            "blackbox",
            "blackbox ai",
            "coding assistant",
            "code completion",
            "ai ide",
            "vscode assistant",
        ),
        build_own_plan=(
            "Use local project index/search, local_code_review, create_gsd_workflow, and git status/diff checks "
            "to provide coding help without uploading project code to a hosted assistant."
        ),
    ),
    ToolCandidate(
        capability="local GSD coding workflow",
        tool="Kattappa plan-execute-verify-fix workflow",
        source="local implementation inspired by Antigravity, GSD, and Ralph coding loops",
        license_note=(
            "Use external coding-agent projects as architecture references only. The core workflow remains "
            "Kattappa-built, local, approval-gated, and test-first."
        ),
        best_for=(
            "antigravity",
            "gsd",
            "get shit done",
            "ralph",
            "autonomous coding loop",
            "plan execute verify fix",
        ),
        build_own_plan=(
            "Use backend.tools.local_creator_tools.create_gsd_workflow to turn a goal into plan, execute, "
            "verify, and fix phases with explicit project boundaries and verification commands."
        ),
    ),
    ToolCandidate(
        capability="local document markdown conversion",
        tool="Kattappa text/HTML/CSV to Markdown fallback",
        source="local fallback with optional Microsoft MarkItDown adapter after approval",
        license_note=(
            "Microsoft MarkItDown is open-source and useful, but Kattappa keeps a built-in fallback first so "
            "PDF/DOCX/PPTX adapters never become mandatory core dependencies."
        ),
        best_for=(
            "markitdown",
            "marketdown",
            "pdf to markdown",
            "docx to markdown",
            "document markdown",
            "convert document",
        ),
        build_own_plan=(
            "Use backend.tools.local_creator_tools.convert_document_text_to_markdown for built-in text, HTML, "
            "and CSV conversion; add MarkItDown only as an optional richer-format adapter after license review."
        ),
    ),
    ToolCandidate(
        capability="local marketing kit",
        tool="Kattappa local brand and campaign draft generator",
        source="local implementation inspired by Pomelli and Ralph eCommerce marketing workflows",
        license_note=(
            "Hosted marketing generators and store automations are not core dependencies. Generate campaign "
            "drafts locally and let each project export or publish manually."
        ),
        best_for=(
            "pomelli",
            "ralph ecommerce",
            "shopify marketing",
            "brand content",
            "ads",
            "social posts",
            "campaign",
        ),
        build_own_plan=(
            "Use backend.tools.local_creator_tools.create_marketing_kit to draft hooks, posts, email subjects, "
            "and CTAs locally without connecting stores, ad accounts, or hosted brand tools."
        ),
    ),
    ToolCandidate(
        capability="safe local network scanner",
        tool="AI Cyber Shield Nmap-compatible local/private scanner",
        source="local implementation with optional Nmap adapter",
        license_note=(
            "Nmap is free for end users, but Cyber Shield keeps its own socket fallback and does not bundle "
            "or require Nmap. Scans are limited to loopback, private, and link-local targets."
        ),
        best_for=(
            "nmap",
            "network scan",
            "open ports",
            "service detection",
            "os detection",
            "port scan",
        ),
        build_own_plan=(
            "Use ai-cyber-shield/asa/network_scan.py for safe local/private TCP checks. If Nmap is installed, "
            "use it as an optional adapter; otherwise use the built-in socket fallback."
        ),
    ),
    ToolCandidate(
        capability="voice-first personal assistant",
        tool="Kattappa local FRIDAY/JARVIS-style desktop assistant",
        source="local implementation inspired by FRIDAY and personal assistant repo patterns",
        license_note=(
            "Do not copy assistant repo code or require hosted Gemini/LiveKit/OpenAI/Sarvam services. Kattappa "
            "keeps voice, screen, memory, and tool routing local with approval gates."
        ),
        best_for=(
            "friday",
            "tony stark",
            "personal assistant",
            "jarvis",
            "voice assistant",
            "open app",
            "screenshot",
        ),
        build_own_plan=(
            "Use Kattappa's local wake-word/STT/TTS pipeline, operator policy, task memory, and tool routes as "
            "the desktop assistant path, adding only repo-native skills with tests."
        ),
    ),
    ToolCandidate(
        capability="local scheduling planner",
        tool="Kattappa local schedule plan + long-task follow-up",
        source="local implementation inspired by Vela scheduling-assistant workflows",
        license_note=(
            "Hosted scheduling agents are not a core dependency. Keep schedules as local tasks, reminders, "
            "calendar-ready text, and approval-gated outbound messages."
        ),
        best_for=("vela", "schedule", "meeting", "calendar", "follow up", "appointment"),
        build_own_plan=(
            "Create local task plans with candidate time windows, follow-up drafts, and durable long-task reminders; "
            "do not connect email/SMS/calendar without explicit approval."
        ),
    ),
    ToolCandidate(
        capability="local workflow queue",
        tool="SQLite job queue with approvals and retries",
        source="local implementation inspired by workflow orchestration patterns",
        license_note=(
            "Avoid cloud queues and restricted core dependencies. Node-RED can stay optional; the default queue "
            "is Kattappa-built and local."
        ),
        best_for=("inngest", "workflow", "background job", "queue", "schedule", "retry", "automation"),
        build_own_plan=(
            "Use SQLite jobs with status, retry count, next_run_at, logs, and approval checkpoints. Expose each "
            "workflow through the existing setup/run path."
        ),
    ),
    ToolCandidate(
        capability="local multi-agent orchestration",
        tool="Kattappa manager-worker loop",
        source="local implementation inspired by Antigravity, TurboQuant, and Odysseus workspace patterns",
        license_note=(
            "Do not copy unknown agent-workspace code or depend on account/cloud platforms. Keep manager-worker "
            "routing, evidence logs, and test gates local."
        ),
        best_for=("antigravity", "turboquant", "turnoquant", "odysseus", "multi-agent", "agent manager"),
        build_own_plan=(
            "Route tasks to specialist workers, record evidence, queue follow-up work, run tests, and ask approval "
            "before applying or publishing improvements."
        ),
    ),
    ToolCandidate(
        capability="portable AI context layer",
        tool="Local MCP context bridge",
        source="https://modelcontextprotocol.io/",
        license_note=(
            "Build this locally with free/open MCP patterns. Do not depend on freemium context services "
            "for the seven-project plan."
        ),
        best_for=("mcp", "context", "memory", "portable", "codex", "claude", "cursor", "notion", "gmail"),
        build_own_plan=(
            "Build our own local MCP context bridge over project index, chat memory, approvals, and notes. "
            "Expose scoped read-only tools first, add source filters, and keep all project context available "
            "without paid accounts or freemium services."
        ),
    ),
    ToolCandidate(
        capability="physical AI world model",
        tool="NVIDIA Cosmos 3 model/reference adapter",
        source="https://github.com/NVIDIA/Cosmos",
        license_note=(
            "Open physical-AI model family with heavy compute needs. Keep it in labs/research paths and inspect "
            "model licenses before downloading weights or building derived datasets."
        ),
        best_for=("robot", "robotics", "camera", "video", "sensor", "physical", "world model", "pcb", "dews"),
        build_own_plan=(
            "Do not make Cosmos 3 a required runtime. Add a lab adapter boundary for future hosted/local inference, "
            "then build lightweight local fallbacks for camera inspection, simulation notes, and sensor-event reasoning."
        ),
    ),
    ToolCandidate(
        capability="screen and cursor guidance",
        tool="OCR + Windows UI Automation adapter",
        source="local adapters: pytesseract, mss, pywinauto, pyautogui",
        license_note="Use small adapters only behind automatic routing and approval-gated desktop actions.",
        best_for=("screen", "cursor", "desktop", "ocr", "guide", "assist"),
        build_own_plan=(
            "Build our own operator policy: screenshot, OCR/accessibility map, target ranking, visual guide, "
            "approval before click/type, and action trace."
        ),
    ),
    ToolCandidate(
        capability="safe BCI research adapter",
        tool="OpenBCI/MNE-style non-invasive research notes",
        source="https://openbci.com/ and https://mne.tools/",
        license_note=(
            "Neuralink/NEO are medical implant-device topics and are blocked from product core. Use only "
            "non-invasive/open research references, no diagnosis, no claims of mind reading or memory upload."
        ),
        best_for=("neuralink", "neuracle", "neo", "bci", "brain computer", "eeg", "openbci", "mne"),
        build_own_plan=(
            "Keep NeuroSeed BCI work to consent-first education/research notes: EEG data literacy, MNE-style "
            "analysis concepts, and safety boundaries. No implant workflow or clinical claim."
        ),
    ),
]


def scout_for_task(task: str, outcome: str = "") -> dict[str, Any]:
    candidate = _pick_candidate(task)
    web_hint = _quick_web_hint(task, candidate.capability)
    existing = memory.list_tool_scout_reports(limit=80)
    duplicate = any(
        item["capability"] == candidate.capability and _similar_task(item["task"], task)
        for item in existing
    )
    if duplicate:
        return {"status": "skipped_duplicate", "capability": candidate.capability}

    title = f"Build own {candidate.capability}"
    motive = f"Task showed this capability may improve Kattappa AI OS: {task[:300]}"
    proposal = (
        f"Candidate: {candidate.tool}\n"
        f"Source/reference: {candidate.source}\n"
        f"Internet hint: {web_hint}\n"
        f"License/safety: {candidate.license_note}\n\n"
        f"Build-own plan:\n{candidate.build_own_plan}\n\n"
        "Rule: do not paste unknown external code. Rebuild the needed behavior locally or use the tool as a replaceable adapter after approval."
    )
    improvement_id = memory.create_improvement(title, motive, proposal, risk="medium")
    report = memory.create_tool_scout_report(
        task=task,
        capability=candidate.capability,
        recommendation=f"Use {candidate.tool} as a reference/adapter for this task type.",
        source=candidate.source,
        license_note=candidate.license_note,
        build_own_plan=candidate.build_own_plan,
        status="proposed",
        improvement_id=improvement_id,
    )
    memory.create_reflection(
        task=f"Tool scout: {candidate.capability}",
        outcome="partial",
        lesson="A free/local improvement candidate was proposed. Build locally where practical; use adapters only after approval.",
    )
    return {"status": "proposed", "report": report, "web_hint": web_hint, "outcome": outcome[:300]}


def scout_for_task_background(task: str, outcome: str = "") -> None:
    thread = threading.Thread(target=_safe_scout, args=(task, outcome), daemon=True)
    thread.start()


def scout_status(limit: int = 25) -> dict[str, Any]:
    reports = memory.list_tool_scout_reports(limit=limit)
    return {
        "mode": "background_free_tool_scout",
        "fully_free_local_first": True,
        "license_safe": True,
        "mission": (
            "For each user task, look for the best fully free/open-source/local-first tool or technology, "
            "whether it runs locally or in the cloud, then propose a build-own implementation or replaceable "
            "adapter after source/license and data-flow inspection. If the named tool is paid, freemium, "
            "trial-limited, reward-based, closed, or privacy-risky, search for a similar free replacement first."
        ),
        "copying_rule": "Do not copy unknown external code. Inspect licenses, learn architecture, then rebuild locally or wrap as an adapter after approval.",
        "reports": reports,
        "catalog": [
            {
                "capability": item.capability,
                "tool": item.tool,
                "source": item.source,
                "license_note": item.license_note,
            }
            for item in CATALOG
        ],
    }


def _safe_scout(task: str, outcome: str) -> None:
    try:
        scout_for_task(task, outcome)
    except Exception:
        return


def _pick_candidate(task: str) -> ToolCandidate:
    lower = task.lower()
    scored: list[tuple[int, ToolCandidate]] = []
    for item in CATALOG:
        score = sum(1 for keyword in item.best_for if keyword in lower)
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else CATALOG[0]


def _quick_web_hint(task: str, capability: str) -> str:
    query = f"best free open source {capability} AI tool"
    try:
        response = httpx.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            timeout=2.5,
            follow_redirects=True,
            headers={"User-Agent": "KattappaAIOS/1.0 local tool scout"},
        )
        response.raise_for_status()
        text = " ".join(response.text.split())
        return text[:700] if text else "No web text returned; use curated local catalog."
    except Exception as exc:
        return f"Web scout unavailable now ({exc}); used curated local free/open-source catalog."


def _similar_task(old: str, new: str) -> bool:
    old_terms = {term for term in old.lower().split() if len(term) > 4}
    new_terms = {term for term in new.lower().split() if len(term) > 4}
    return bool(old_terms and len(old_terms & new_terms) >= 3)
