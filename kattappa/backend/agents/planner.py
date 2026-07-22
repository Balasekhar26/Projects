from __future__ import annotations

from dataclasses import dataclass
import json
import time
import uuid
from typing import Any, Optional

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
            "chrome",
            "browser",
            "speedtest",
            "speed test",
            "internet speed",
            "speed",
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
            "chrome",
            "browser",
            "screenshot",
            "calculator",
            "active window",
            "open applications",
            "open window",
            "applications are currently open",
            "currently active window",
            "open a terminal",
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
            "git status",
            "run git",
            "run the test suite",
            "test suite",
            "run tests",
            "git",
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
        ("file", "folder", "read ", "write", "save", "rename", "path", "directory", "list all files", "list files", "find all python", "find", "search", "search the project", "search project", "find all todo", "todo", "codebase", "show", "lines", "show me", "read"),
        2,
    ),
    AgentProfile(
        "memory",
        "stores or recalls personal preferences, facts, and past interactions",
        (
            "remember",
            "recall",
            "memorize",
            "forget",
            "my name",
            "favorite color",
            "know about me",
            "preference",
        ),
        4,
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


@dataclass
class TaskStep:
    step_id: str
    description: str
    agent: str
    action: str
    params: dict[str, Any]
    dependencies: list[str]
    risk_level: str = "LOW"
    approval_required: bool = False
    estimated_resources: dict[str, Any] = None
    failure_recovery: dict[str, Any] = None
    rollback_step: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "agent": self.agent,
            "action": self.action,
            "params": self.params,
            "dependencies": self.dependencies,
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "estimated_resources": self.estimated_resources or {},
            "failure_recovery": self.failure_recovery or {},
            "rollback_step": self.rollback_step
        }


class TaskGraph:
    def __init__(self, goal: str):
        self.goal = goal
        self.steps: dict[str, TaskStep] = {}

    def add_step(self, step: TaskStep) -> None:
        self.steps[step.step_id] = step

    def get_step(self, step_id: str) -> TaskStep:
        return self.steps[step_id]

    def has_cycle(self) -> bool:
        visited = {}
        for step_id in self.steps:
            visited[step_id] = 0

        def dfs(u: str) -> bool:
            visited[u] = 1
            for v in self.steps[u].dependencies:
                if v not in self.steps:
                    continue
                if visited[v] == 1:
                    return True
                if visited[v] == 0:
                    if dfs(v):
                        return True
            visited[u] = 2
            return False

        for step_id in self.steps:
            if visited[step_id] == 0:
                if dfs(step_id):
                    return True
        return False

    def topological_sort(self) -> list[str]:
        if self.has_cycle():
            raise ValueError("Circular dependency detected in task graph")
        
        visited = set()
        order = []

        def dfs(u: str) -> None:
            visited.add(u)
            for v in self.steps[u].dependencies:
                if v in self.steps and v not in visited:
                    dfs(v)
            order.append(u)

        for step_id in self.steps:
            if step_id not in visited:
                dfs(step_id)
        return order


class PlannerAgent:
    def __init__(self):
        pass

    def decompose(self, goal: str, context: dict[str, Any] = None) -> TaskGraph:
        from backend.core.planner.planner_engine import PlannerEngine
        graph = PlannerEngine.decompose(goal, context)
        for step_id, step in graph.steps.items():
            self.estimate_resources(step)
            self.insert_approval_gates(step)
            step.rollback_step = self.generate_rollback_step(step)
            step.failure_recovery = self.generate_failure_recovery(step)

        return graph

    def estimate_resources(self, step: TaskStep) -> dict[str, Any]:
        estimated = {
            "tokens": 2000,
            "disk_bytes": 0,
            "network_requests": 0,
            "concurrent_tasks": 0,
        }
        action_upper = step.action.upper()
        if action_upper in ("WRITE_FILE", "CREATE_FILE", "FILE_WRITE", "FILE_MODIFY", "PATCH_CODE"):
            content = step.params.get("code") or step.params.get("content") or ""
            estimated["disk_bytes"] = len(content.encode("utf-8"))
            estimated["tokens"] = 3000
            estimated["concurrent_tasks"] = 1
        elif action_upper in ("RUN_TESTS", "DEPLOY"):
            estimated["tokens"] = 4000
            estimated["concurrent_tasks"] = 1
        elif action_upper in ("BROWSER_SEARCH", "BROWSER_READ", "BROWSER_NAVIGATE", "BROWSER_MAP_LINKS"):
            estimated["network_requests"] = 2
            estimated["tokens"] = 3000
        elif action_upper in ("COMMIT_MEMORY_DELTA"):
            content = step.params.get("content") or ""
            estimated["disk_bytes"] = len(content.encode("utf-8"))
            estimated["tokens"] = 1000
        elif action_upper in ("DELETE_MEMORY", "ROLLBACK_MEMORY", "PIN_MEMORY", "UNPIN_MEMORY", "EXPIRE_MEMORY", "CONSOLIDATE_MEMORY", "AGING_MEMORY"):
            estimated["tokens"] = 500

        step.estimated_resources = estimated

        try:
            from backend.core.resource_governor import ResourceGovernor
            status = ResourceGovernor.get_status()
            
            if status.get("system_cpu_percent", 0) > ResourceGovernor.CPU_LIMIT_PERCENT:
                estimated["warning"] = "CPU usage is near limit"
            if status.get("system_ram_available_mb", 9999) < ResourceGovernor.RAM_LIMIT_MIN_AVAILABLE_MB:
                estimated["warning"] = "RAM usage is near limit"
                
            if estimated["disk_bytes"] > 0:
                if status["disk_used_bytes"] + estimated["disk_bytes"] > ResourceGovernor.DISK_LIMIT_BYTES:
                    estimated["valid"] = False
                    estimated["error"] = "Disk quota exceeded"
                    return estimated
            
            if estimated["network_requests"] > 0:
                if status["network_requests"] + estimated["network_requests"] > ResourceGovernor.NETWORK_LIMIT_REQUESTS:
                    estimated["valid"] = False
                    estimated["error"] = "Network requests quota exceeded"
                    return estimated

            if estimated["concurrent_tasks"] > 0:
                if status["concurrent_tasks"] >= ResourceGovernor.CONCURRENT_TASKS_LIMIT:
                    estimated["warning"] = "Concurrent tasks limit reached, task might be delayed"
                    
            estimated["valid"] = True
        except Exception as e:
            estimated["valid"] = True
            estimated["error"] = f"Resource check error: {e}"

        return estimated

    def insert_approval_gates(self, step: TaskStep) -> None:
        from backend.core.action_broker import ActionBroker
        risk_level = ActionBroker.get_risk_level(step.action, step.params)
        step.risk_level = risk_level
        if risk_level in ("MEDIUM", "HIGH"):
            step.approval_required = True
        else:
            step.approval_required = False

    def generate_rollback_step(self, step: TaskStep) -> dict[str, Any] | None:
        action_upper = step.action.upper()
        if action_upper in ("WRITE_FILE", "CREATE_FILE", "FILE_WRITE", "FILE_MODIFY"):
            target = step.params.get("target") or step.params.get("path")
            if target:
                return {
                    "action": "DELETE_FILE",
                    "params": {"target": target}
                }
        elif action_upper == "PIN_MEMORY":
            memory_id = step.params.get("memory_id")
            if memory_id:
                return {
                    "action": "UNPIN_MEMORY",
                    "params": {"memory_id": memory_id}
                }
        elif action_upper == "COMMIT_MEMORY_DELTA":
            memory_id = step.params.get("memory_id")
            if memory_id:
                return {
                    "action": "DELETE_MEMORY",
                    "params": {"memory_id": memory_id}
                }
        return None

    def generate_failure_recovery(self, step: TaskStep) -> dict[str, Any]:
        action_upper = step.action.upper()
        if action_upper == "RUN_TESTS":
            return {
                "strategy": "debug_and_retry",
                "max_attempts": 2,
                "fallback_action": "ANALYZE_CODE"
            }
        elif action_upper in ("WRITE_FILE", "CREATE_FILE", "FILE_WRITE", "FILE_MODIFY"):
            return {
                "strategy": "retry",
                "max_attempts": 3,
                "fallback_action": None
            }
        elif action_upper in ("BROWSER_SEARCH", "BROWSER_READ"):
            return {
                "strategy": "alternative_engine",
                "max_attempts": 2,
                "fallback_action": "BROWSER_NAVIGATE"
            }
        return {
            "strategy": "abort",
            "max_attempts": 1,
            "fallback_action": None
        }

    def log_plan_history(self, graph: TaskGraph, state: dict[str, Any]) -> None:
        try:
            from backend.core.memory_service import MemoryService
            steps_summary = []
            for step_id in graph.topological_sort():
                step = graph.get_step(step_id)
                steps_summary.append(f"{step.step_id} ({step.agent}): {step.description}")
            
            plan_content = (
                f"Remember plan execution for goal: {graph.goal}\n"
                f"Execution steps:\n" + "\n".join(f"- {s}" for s in steps_summary)
            )
            log_state = dict(state) if state else {}
            log_state["approved"] = True
            MemoryService.write(
                agent="planner",
                content=plan_content,
                memory_type="procedural",
                source="system",
                state=log_state
            )
        except Exception:
            pass


def planner_node(state):
    import uuid
    import re
    import os
    from backend.planner.gtpyhop_adapter import GTPyhopAdapter
    from backend.planner.task_decomposer import TaskDecomposer, Operator, Method
    from backend.planner.goal_stack import GoalItem

    user_input = state["user_input"]
    logs = state.setdefault("logs", [])
    logs.append("planner: entering persistent HTN planner node")

    # 1. Goal Extraction (TASK 3)
    extracted_goals = []
    lower_input = user_input.lower().strip()
    compound_web_download = (
        "download" in lower_input
        and any(token in lower_input for token in ("website", "web page", "url"))
    )
    if compound_web_download:
        extracted_goals.append("acquire_web_document")
    if "meeting" in lower_input or "schedule" in lower_input or "book" in lower_input:
        extracted_goals.append("schedule_meeting")
    if "install" in lower_input:
        extracted_goals.append("install_software")
    if "verify" in lower_input or "version" in lower_input:
        extracted_goals.append("verify_installation")
    
    from backend.agents.planner import route_task
    routed = route_task(user_input)
    specialist_agent = routed.get("agent") if routed else None

    if not extracted_goals:
        if specialist_agent and specialist_agent != "evaluator":
            extracted_goals.append(f"execute_{specialist_agent}")
        else:
            # Fallback to general task goals
            extracted_goals.append("compile_code")
            extracted_goals.append("run_tests")
            extracted_goals.append("deploy_binary")

    logs.append(f"planner: extracted goals {extracted_goals}")

    # 2. HTN Planner Setup & Decomposition (TASK 2)
    decomposer = TaskDecomposer()
    
    # Declare operators and methods matching our domains
    decomposer.declare_operator(Operator("check_calendar", {}, {"calendar_checked": True}, estimated_cost=1.0, estimated_time=1.0))
    decomposer.declare_operator(Operator("reserve_slot", {"calendar_checked": True}, {"meeting_booked": True}, estimated_cost=2.0, estimated_time=2.0))
    decomposer.declare_operator(Operator("download_package", {}, {"package_downloaded": True}, estimated_cost=3.0, estimated_time=5.0))
    decomposer.declare_operator(Operator("run_installer", {"package_downloaded": True}, {"software_installed": True}, estimated_cost=4.0, estimated_time=10.0))
    decomposer.declare_operator(Operator("query_version_command", {"software_installed": True}, {"version_verified": True}, estimated_cost=1.0, estimated_time=2.0))
    decomposer.declare_operator(Operator("compile_code", {"has_source": True}, {"code_compiled": True}, estimated_cost=2.0, estimated_time=5.0))
    decomposer.declare_operator(Operator("run_tests", {"code_compiled": True}, {"tests_passed": True}, estimated_cost=1.0, estimated_time=3.0))
    decomposer.declare_operator(Operator("deploy_binary", {"tests_passed": True}, {"app_deployed": True}, estimated_cost=5.0, estimated_time=8.0))
    decomposer.declare_operator(Operator("open_target_website", {}, {"website_opened": True}, estimated_cost=1.0, estimated_time=2.0))
    decomposer.declare_operator(Operator("store_downloaded_document", {"website_opened": True}, {"document_stored": True}, estimated_cost=2.0, estimated_time=4.0))

    # Declare methods decomposing high-level tasks
    decomposer.declare_method(Method("do_schedule", "schedule_meeting", {}, ["check_calendar", "reserve_slot"]))
    decomposer.declare_method(Method("do_install", "install_software", {}, ["download_package", "run_installer"]))
    decomposer.declare_method(Method("do_verify", "verify_installation", {"software_installed": True}, ["query_version_command"]))
    decomposer.declare_method(Method("do_compile", "compile_code", {}, ["compile_code"]))
    decomposer.declare_method(Method("do_test", "run_tests", {}, ["run_tests"]))
    decomposer.declare_method(Method("do_deploy", "deploy_binary", {}, ["deploy_binary"]))
    decomposer.declare_method(Method("do_web_download", "acquire_web_document", {}, ["open_target_website", "store_downloaded_document"]))
    
    if specialist_agent and specialist_agent != "evaluator" and f"execute_{specialist_agent}" in extracted_goals:
        goal_name = f"execute_{specialist_agent}"
        decomposer.declare_operator(Operator(goal_name, {}, {f"{specialist_agent}_done": True}, estimated_cost=1.0, estimated_time=1.0))
        decomposer.declare_method(Method(f"do_{specialist_agent}", goal_name, {}, [goal_name]))

    # Goal compound task
    decomposer.declare_method(Method(
        name="execute_kattappa_mission",
        task_name="kattappa_mission",
        preconditions={},
        subtasks=extracted_goals
    ))

    # Initial state preparation
    initial_state = {
        "has_source": True,
        "has_ticket": False,
        "calendar_checked": False,
        "package_downloaded": False,
        "software_installed": True if "verify" in lower_input and "install" not in lower_input else False,
        "code_compiled": False,
        "tests_passed": False,
        "website_opened": False,
        "document_stored": False,
    }

    adapter = GTPyhopAdapter(decomposer=decomposer)
    
    # Check if there is a saved checkpoint to restore from (TASK 7)
    checkpoint_file = "planner_checkpoint.bin"
    if os.path.exists(checkpoint_file):
        logs.append("planner: found checkpoint, restoring planner state...")
        try:
            with open(checkpoint_file, "rb") as f:
                checkpoint_data = f.read()
            adapter.restore(checkpoint_data)
            logs.append("planner: restored checkpoint successfully")
        except Exception as e:
            logs.append(f"planner: failed to restore checkpoint: {e}")

    try:
        plan = adapter.create_plan(
            goal="kattappa_mission",
            world_state=initial_state,
            constraints={"timeout": 60.0, "priority": "HIGH"}
        )
    except Exception as e:
        logs.append(f"planner: fallback to base planner because of error: {e}")
        plan = {
            "steps": [
                {
                    "name": "compile_code",
                    "preconditions": {"has_source": True},
                    "effects": {"code_compiled": True},
                    "estimated_cost": 2.0,
                    "estimated_time": 5.0
                }
            ]
        }

    # Populate TASK 2 output variables
    state["goal_tree"] = extracted_goals
    state["execution_plan"] = [step["name"] for step in plan["steps"]]
    state["utility_score"] = float(sum(step["estimated_cost"] for step in plan["steps"]))
    state["risk_score"] = float(len(plan["steps"]) * 0.1)

    # 3. Tool Routing mapping (TASK 4)
    mapping = {
        "download_package": "browser",
        "run_installer": "terminal",
        "query_version_command": "terminal",
        "check_calendar": "memory",
        "reserve_slot": "memory",
        "compile_code": "coder",
        "run_tests": "terminal",
        "deploy_binary": "builder",
        "open_target_website": "browser",
        "store_downloaded_document": "file",
    }
    if specialist_agent and specialist_agent != "evaluator":
        mapping[f"execute_{specialist_agent}"] = specialist_agent
    
    execution_steps = [mapping.get(step["name"], "evaluator") for step in plan["steps"]]
    state["execution_steps"] = execution_steps
    selected = execution_steps.pop(0) if execution_steps else "evaluator"
    state["selected_agent"] = selected
    
    plan_label = "Chained execution plan" if compound_web_download else "HTN Plan"
    state["plan"] = f"{plan_label}: {' -> '.join(state['execution_plan'])} (Utility: {state['utility_score']:.2f})"
    state["operator_plan"] = build_operator_plan(user_input, selected, state.get("memory_context"))

    # Populate task_graph for TaskGraph compatibility and log plan history via public MemoryService API
    try:
        agent_inst = PlannerAgent()
        tg = agent_inst.decompose(user_input, context=state.get("memory_context") or {})
        if tg and tg.steps:
            state["task_graph"] = {step_id: step.__dict__ for step_id, step in tg.steps.items()}
            agent_inst.log_plan_history(tg, state)
        else:
            raise ValueError("TaskGraph decomposition returned empty steps")
    except Exception as exc:
        logs.append(f"planner: TaskGraph decomposition fallback triggered for {user_input!r}: {exc}")
        fallback_graph = {}
        for idx, step_name in enumerate(state.get("execution_plan", []), 1):
            step_id = f"step_{idx}"
            fallback_graph[step_id] = {
                "step_id": step_id,
                "description": f"Execute planned step: {step_name}",
                "provenance": "goal_derived_fallback",
            }
        state["task_graph"] = fallback_graph

    logs.append(f"planner: plan generation complete, initial routing to '{selected}', remaining steps queue: {execution_steps}")

    return state



def _direct_route(lower: str) -> dict[str, object] | None:
    if (
        lower.startswith(
            (
                "remember ",
                "remember that ",
                "remember this ",
                "please remember ",
                "save this memory",
                "store this memory",
                "keep in memory",
            )
        )
        or "remember that" in lower
        or "remember this" in lower
        or "save in memory" in lower
        or "remember" in lower
    ):
        return {
            "agent": "memory",
            "reason": "Explicit user memory command.",
            "scores": [],
        }

    if any(word in lower for word in ("delete", "remove", "erase", "rename")) or ("create" in lower and "file" in lower) or ("write" in lower and "file" in lower):
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
            "screenshot",
            "take a screenshot",
            "applications are currently open",
            "currently open",
            "active window",
            "open window",
            "applications",
        )
    )
    if desktop_action:
        return {
            "agent": "desktop",
            "reason": "Desktop/cursor action should use the desktop guidance and approval path.",
            "scores": [],
        }

    return None
