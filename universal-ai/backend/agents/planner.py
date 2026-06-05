from __future__ import annotations

from dataclasses import dataclass

from backend.core.operator import build_operator_plan


@dataclass(frozen=True)
class AgentProfile:
    name: str
    purpose: str
    keywords: tuple[str, ...]
    weight: int = 1


AGENT_PROFILES = [
    AgentProfile(
        "builder",
        "understands this project's files, architecture, workflow, launch/debug process, and safe build loop",
        (
            "how you work",
            "your workflow",
            "codex",
            "builder brain",
            "your files",
            "your code",
            "analyze this project",
            "this project",
            "architecture",
        ),
        4,
    ),
    AgentProfile(
        "researcher",
        "searches or summarizes internet/current information",
        (
            "research",
            "search web",
            "google",
            "latest",
            "internet",
            "online",
            "web search",
            "current",
            "2026",
        ),
        4,
    ),
    AgentProfile(
        "browser",
        "opens or reads a specific website, URL, or web page",
        (
            "browse",
            "website",
            "url",
            "web page",
            "open http",
            "read this page",
            "localhost",
        ),
        3,
    ),
    AgentProfile(
        "coder",
        "handles programming, debugging, embedded/electronics explanations, tests, and technical implementation",
        (
            "code",
            "bug",
            "test",
            "refactor",
            "python",
            "typescript",
            "react",
            "embedded",
            "embeded",
            "electronics",
            "microcontroller",
            "firmware",
            "pcb",
            "sensor",
            "iot",
            "api",
        ),
        3,
    ),
    AgentProfile(
        "vision",
        "analyzes screen, screenshot, OCR, image, or visual UI state",
        (
            "screen",
            "screenshot",
            "ocr",
            "look at",
            "image",
            "camera",
            "visual",
            "see this",
        ),
        3,
    ),
    AgentProfile(
        "desktop",
        "guides or controls desktop actions through observe/guide/assist/autonomous modes",
        (
            "desktop",
            "click",
            "type into",
            "press key",
            "cursor",
            "open app",
            "select",
            "drag",
        ),
        3,
    ),
    AgentProfile(
        "terminal",
        "runs or evaluates shell, PowerShell, command-line, and local process tasks",
        (
            "terminal",
            "powershell",
            "run command",
            "cmd",
            "command prompt",
            "pytest",
            "npm run",
            "ollama pull",
        ),
        3,
    ),
    AgentProfile(
        "finance",
        "analyzes OHLCV/K-line market candles with the local Finance Brain and optional Kronos adapter",
        (
            "kronos",
            "ohlcv",
            "k-line",
            "candlestick",
            "candles",
            "btc",
            "crypto",
            "stock",
            "market forecast",
            "trading",
            "finance brain",
        ),
        4,
    ),
    AgentProfile(
        "self_improver",
        "creates approval-gated self-improvement proposals, draft skills, and evolution tasks",
        (
            "improve yourself",
            "self-improve",
            "self improvement",
            "evolve",
            "make yourself better",
            "new skill",
        ),
        4,
    ),
    AgentProfile(
        "voice",
        "handles speech, wake word, transcription, TTS, and voice assistant readiness",
        (
            "voice",
            "transcribe",
            "speak",
            "wake word",
            "tts",
            "stt",
            "microphone",
            "audio",
        ),
        3,
    ),
    AgentProfile(
        "file",
        "plans file/folder inspection and safe file operations",
        ("file", "folder", "read ", "write", "save", "rename", "path", "directory"),
        2,
    ),
]


def route_task(text: str) -> dict[str, object]:
    lower = text.lower()
    scores: list[dict[str, object]] = []
    for profile in AGENT_PROFILES:
        matches = [keyword for keyword in profile.keywords if keyword in lower]
        score = len(matches) * profile.weight
        scores.append(
            {
                "agent": profile.name,
                "score": score,
                "matches": matches,
                "purpose": profile.purpose,
            }
        )

    scores.sort(key=lambda item: int(item["score"]), reverse=True)
    best = scores[0]
    if int(best["score"]) <= 0:
        return {
            "agent": "evaluator",
            "reason": "No specialist matched strongly; answering directly with memory context.",
            "scores": scores,
        }

    return {
        "agent": best["agent"],
        "reason": f"Selected {best['agent']} because matched: {', '.join(best['matches'])}.",
        "scores": scores,
    }


def planner_node(state):
    routing = route_task(state["user_input"])
    selected = str(routing["agent"])
    state["selected_agent"] = selected
    state["tool_request"] = {"agent_routing": routing}
    if selected == "evaluator":
        state["plan"] = str(routing["reason"])
    else:
        state["plan"] = (
            f"{routing['reason']} Route to {selected} agent, then safety-check before tool execution."
        )
    state["operator_plan"] = build_operator_plan(
        state["user_input"], state["selected_agent"], state.get("memory_context")
    )
    state["logs"].append(f"planner: {selected} - {routing['reason']}")
    return state
