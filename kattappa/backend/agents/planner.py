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
            "rival",
            "rival to you",
            "what can you do",
            "list out what can",
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
        "guides or controls desktop actions through automatic routing and approval gates",
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
    direct = _direct_route(lower)
    if direct:
        return direct

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


PLANNER_SYSTEM_PROMPT = (
    "You are the Kattappa AI OS Planner. Your goal is to analyze the user's request and context, "
    "and draft a structured execution plan. Choose the best specialist agent for the task.\n"
    "Available Specialist Agents:\n"
    "- coder: for coding, debugging, electronics, APIs, test files.\n"
    "- builder: for project file map, workspace architecture, launch/build tasks.\n"
    "- researcher: for general knowledge, google/web search, online queries.\n"
    "- browser: for specific URL loading or viewing pages.\n"
    "- desktop: for GUI, clicking, typing, cursor movements.\n"
    "- terminal: for running commands, subprocesses, terminal scripting.\n"
    "- file: for reading, writing, copying, deleting local files.\n"
    "- vision: for images, screen snapshots, OCR details.\n"
    "- finance: for OHLCV candlestick market forecasting.\n"
    "- self_improver: for custom skills, self-evolution ideas.\n"
    "- voice: for audio, speech synthesis/recognition.\n"
    "- evaluator: default agent for answering general questions or when no other agent matches.\n"
    "\n"
    "Provide your response EXACTLY in this format:\n"
    "[Reasoning] Your explanation of why you selected the agent and what you need to verify.\n"
    "[Routing] the_selected_agent_name\n"
    "[Checklist]\n"
    "- Step 1: Brief task step\n"
    "- Step 2: Brief task step\n"
)


def parse_reasoning_plan(text: str) -> dict[str, Any]:
    from typing import Any
    routing = "evaluator"
    reasoning = ""
    checklist = []
    
    current_section = None
    for line in text.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        if line_str.lower().startswith("[reasoning]"):
            current_section = "reasoning"
            val = line_str[11:].strip()
            if val:
                reasoning = val
        elif line_str.lower().startswith("[routing]"):
            current_section = "routing"
            val = line_str[9:].strip().lower()
            if val:
                val = val.replace(".", "").replace("agent", "").strip()
                routing = val
        elif line_str.lower().startswith("[checklist]"):
            current_section = "checklist"
        elif line_str.startswith("-"):
            if current_section == "checklist":
                checklist.append(line_str[1:].strip())
        else:
            if current_section == "reasoning":
                reasoning += " " + line_str
            elif current_section == "routing":
                routing = line_str.lower().replace(".", "").replace("agent", "").strip()
                
    return {
        "reasoning": reasoning.strip(),
        "agent": routing,
        "checklist": checklist
    }


def planner_node(state):
    from typing import Any
    if state.get("result") and state.get("selected_agent"):
        state["tool_request"] = state.get("tool_request") or {
            "agent_routing": {
                "agent": state["selected_agent"],
                "reason": "Handled directly before planner routing.",
                "scores": [],
            }
        }
        state["plan"] = state.get("plan") or "Direct command already handled."
        state["operator_plan"] = build_operator_plan(
            state["user_input"], state["selected_agent"], state.get("memory_context")
        )
        state["logs"].append(f"planner: preserved direct handler {state['selected_agent']}")
        return state

    routing = route_task(state["user_input"])
    selected = str(routing["agent"])
    reason = str(routing["reason"])

    lower_input = state["user_input"].lower().strip()
    direct_routing = _direct_route(lower_input)
    is_simple = (
        len(lower_input) < 60
        or lower_input in {"hi", "hello", "hey", "status"}
        or any(phrase in lower_input for phrase in ["tell a joke", "tell me a joke", "write a poem", "open chrome", "what time", "about yourself"])
    )
    if is_simple:
        if direct_routing:
            selected = str(direct_routing["agent"])
            reason = str(direct_routing["reason"])
        state["selected_agent"] = selected
        state["tool_request"] = {"agent_routing": {"agent": selected, "reason": reason, "scores": []}}
        state["plan"] = reason
        state["operator_plan"] = build_operator_plan(
            state["user_input"], state["selected_agent"], state.get("memory_context")
        )
        state["logs"].append(f"planner (fast-pass): {selected} - {reason}")
        return state

    state["logs"].append(f"planner: generating multi-step reasoning plan for agent '{selected}'...")
    prompt = (
        f"User Request:\n{state['user_input']}\n\n"
        f"Memory Context / Workspace Info:\n{state.get('memory_context') or 'No context available.'}\n\n"
        f"Selected Agent for execution: {selected}\n\n"
        "Draft a reasoning statement and a step-by-step checklist for this request."
    )
    
    try:
        from backend.core.model_router import ask_model
        plan_text = ask_model(prompt, role="fast", system=PLANNER_SYSTEM_PROMPT)
        parsed = parse_reasoning_plan(plan_text)
        
        reason = parsed["reasoning"] or reason
        checklist = parsed["checklist"]
        if not checklist:
            checklist = [f"Execute request using the {selected} agent."]
            
        state["selected_agent"] = selected
        state["plan"] = f"Reasoning Plan: {reason}\nChecklist:\n" + "\n".join(f"- {step}" for step in checklist)
        state["tool_request"] = {
            "agent_routing": {
                "agent": selected,
                "reason": reason,
                "scores": routing.get("scores", []),
                "checklist": checklist,
                "cot_reasoning": parsed["reasoning"]
            }
        }
        state["logs"].append(f"planner (CoT): routed to {selected} agent")
        
    except Exception as exc:
        state["selected_agent"] = selected
        state["tool_request"] = {"agent_routing": routing}
        state["plan"] = f"Planner fallback (Error: {exc}): {reason}"
        state["logs"].append(f"planner (fallback): routed to {selected} agent")

    state["operator_plan"] = build_operator_plan(
        state["user_input"], state["selected_agent"], state.get("memory_context")
    )
    return state


def _direct_route(lower: str) -> dict[str, object] | None:
    if lower.startswith(
        (
            "remember ",
            "remember that ",
            "remember this ",
            "please remember ",
            "save this memory",
            "store this memory",
            "keep in memory",
        )
    ):
        return {
            "agent": "memory",
            "reason": "Explicit user memory command.",
            "scores": [],
        }

    if any(word in lower for word in ("delete", "remove", "erase", "rename")):
        return {
            "agent": "file",
            "reason": "File or data-changing verb needs the file/action safety path.",
            "scores": [],
        }

    desktop_action = any(
        phrase in lower
        for phrase in (
            "cursor",
            "where to click",
            "guide me",
            "click",
            "type into",
            "press key",
            "open app",
            "select",
            "drag",
        )
    )
    if desktop_action:
        return {
            "agent": "desktop",
            "reason": "Desktop/cursor action should use the desktop guidance and approval path.",
            "scores": [],
        }

    return None
