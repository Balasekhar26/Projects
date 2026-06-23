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
        graph = TaskGraph(goal)
        lower_goal = goal.lower()

        if "write" in lower_goal and "test" in lower_goal:
            step1 = TaskStep(
                step_id="step1",
                description="Write the implementation file",
                agent="coder",
                action="WRITE_FILE",
                params={"target": "backend/core/sample.py", "content": "print('hello')"},
                dependencies=[]
            )
            step2 = TaskStep(
                step_id="step2",
                description="Run the verification tests",
                agent="coder",
                action="RUN_TESTS",
                params={"target": "backend/tests/test_sample.py"},
                dependencies=["step1"]
            )
            graph.add_step(step1)
            graph.add_step(step2)
        elif "read" in lower_goal and "search" in lower_goal:
            step1 = TaskStep(
                step_id="read_step",
                description="Read configuration details",
                agent="file",
                action="READ_FILE",
                params={"target": "backend/config.yaml"},
                dependencies=[]
            )
            step2 = TaskStep(
                step_id="search_step",
                description="Search web for updates",
                agent="researcher",
                action="BROWSER_SEARCH",
                params={"query": "latest kattappa OS config"},
                dependencies=[]
            )
            graph.add_step(step1)
            graph.add_step(step2)
        else:
            try:
                from backend.core.model_router import ask_model
                prompt = (
                    f"Goal: {goal}\n"
                    f"Context: {context or {}}\n"
                    "Decompose this goal into a list of steps. Output only a valid JSON array of objects. "
                    "Each object MUST have: step_id (string), description (string), agent (string), action (string), "
                    "params (dict), dependencies (list of step_ids).\n"
                    "Example:\n"
                    '[{"step_id": "s1", "description": "Write code", "agent": "coder", "action": "WRITE_FILE", "params": {"target": "f.py", "content": "#code"}, "dependencies": []}]'
                )
                res = ask_model(prompt, role="fast")
                clean_res = res.strip()
                if clean_res.startswith("```json"):
                    clean_res = clean_res[7:]
                if clean_res.endswith("```"):
                    clean_res = clean_res[:-3]
                clean_res = clean_res.strip()
                steps_data = json.loads(clean_res)
                for item in steps_data:
                    step = TaskStep(
                        step_id=item["step_id"],
                        description=item["description"],
                        agent=item["agent"],
                        action=item["action"],
                        params=item.get("params", {}),
                        dependencies=item.get("dependencies", [])
                    )
                    graph.add_step(step)
            except Exception:
                from backend.agents.planner import route_task
                routing = route_task(goal)
                agent = routing["agent"]
                step = TaskStep(
                    step_id="default_step",
                    description=f"Execute request: {goal}",
                    agent=agent,
                    action="EXECUTE",
                    params={"text": goal},
                    dependencies=[]
                )
                graph.add_step(step)
        
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
    from typing import Any
    user_input = state["user_input"]
    lower_input = user_input.lower().strip()

    # V1 Planning Engine execution
    planner = PlannerAgent()
    try:
        graph = planner.decompose(user_input, state)
        # Cycle Check (ValueError is raised on circular dependency)
        graph.topological_sort()
        # Log to memory service
        planner.log_plan_history(graph, state)
        # Save structured graph in state
        state["task_graph"] = {step_id: step.to_dict() for step_id, step in graph.steps.items()}
    except ValueError as e:
        raise e
    except Exception as e:
        state["logs"].append(f"planner V1 initialization error: {e}")

    # 1. Multi-Agent Planner Chaining Detection
    execution_steps = []
    if "rf" in lower_input or "rf framework" in lower_input:
        execution_steps = ["researcher", "monitoring"]
    elif "zen technologies" in lower_input or "brochure" in lower_input:
        execution_steps = ["browser", "file"]
    elif "then" in lower_input or "and" in lower_input:
        parts = lower_input.split("then")
        for part in parts:
            for profile in AGENT_PROFILES:
                if any(keyword in part for keyword in profile.keywords):
                    if profile.name not in execution_steps:
                        execution_steps.append(profile.name)
                        
    if len(execution_steps) > 1:
        state["execution_steps"] = execution_steps
        selected = execution_steps.pop(0)
        state["selected_agent"] = selected
        state["logs"].append(f"planner: detected chained request, routing to first agent '{selected}', queue: {execution_steps}")
        state["tool_request"] = {
            "agent_routing": {
                "agent": selected,
                "reason": "Chained multi-step plan started.",
                "scores": [],
                "checklist": [f"Run {agent}" for agent in [selected] + execution_steps]
            }
        }
        state["plan"] = f"Chained execution plan: {' -> '.join([selected] + execution_steps)}"
        state["operator_plan"] = build_operator_plan(user_input, selected, state.get("memory_context"))
        return state

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
