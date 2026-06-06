from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, StateGraph

from ai_system.agents.tasks import TaskRun, TaskStore
from ai_system.core.events import EventLog
from ai_system.core.llm import LocalLLM
from ai_system.memory.store import MemoryStore
from ai_system.tools.registry import ToolRegistry


SYSTEM_PROMPT = """You are the master agent for a local-first personal AI OS.
Work like a careful engineering assistant. Use recalled memory when useful.
Prefer practical, step-by-step answers. Ask before risky desktop, shell, or account actions.
"""


class AgentState(TypedDict):
    user_input: str
    recalled_memory: list[str]
    response: str
    mode: str


@dataclass
class MasterAgent:
    llm: LocalLLM
    memory: MemoryStore

    def __post_init__(self) -> None:
        self.tools = ToolRegistry(self.llm.settings, self.memory)
        self.events = EventLog()
        self.tasks = TaskStore()
        graph = StateGraph(AgentState)
        graph.add_node("recall", self._recall)
        graph.add_node("answer", self._answer)
        graph.set_entry_point("recall")
        graph.add_edge("recall", "answer")
        graph.add_edge("answer", END)
        self.graph = graph.compile()

    def _recall(self, state: AgentState) -> AgentState:
        state["recalled_memory"] = self.memory.recall(state["user_input"], limit=5)
        return state

    def _answer(self, state: AgentState) -> AgentState:
        memory_text = "\n".join(f"- {item}" for item in state["recalled_memory"]) or "No relevant memory found."
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Relevant memory:\n{memory_text}\n\nUser request:\n{state['user_input']}",
            },
        ]
        state["response"] = self.llm.chat(messages, mode=state.get("mode", "planner"))
        self.memory.remember(f"User: {state['user_input']}\nAssistant: {state['response']}", kind="conversation")
        return state

    def ask(self, user_input: str, mode: str = "planner") -> str:
        result = self.graph.invoke(
            {"user_input": user_input, "recalled_memory": [], "response": "", "mode": mode}
        )
        return result["response"]

    def plan(self, goal: str) -> list[str]:
        prompt = """Create a concise execution plan for this goal.
Return only JSON like {"steps": ["step 1", "step 2"]}. Keep it under 8 steps.
Do not include shell commands unless explicitly needed.
"""
        raw = self.llm.chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": goal},
            ],
            mode="planner",
        )
        try:
            data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
            steps = [str(step) for step in data.get("steps", []) if str(step).strip()]
        except Exception:
            steps = [line.strip("- ").strip() for line in raw.splitlines() if line.strip()]
        return steps[:8] or ["Clarify goal", "Execute safest useful next action", "Summarize result"]

    def run_task(self, goal: str, execute_tools: bool = False) -> TaskRun:
        run = self.tasks.create(goal, self.plan(goal))
        self.events.write("task_started", f"{run.id}: {goal}")

        for step in run.steps:
            step.status = "running"
            self.tasks.save(run)
            tool_text = ""
            if execute_tools:
                tool_text = self._maybe_use_tool(goal, step.title)
            step.result = self.ask(
                f"Goal: {goal}\nCurrent step: {step.title}\nTool result if any:\n{tool_text}\n"
                "Complete this step concisely. If action is unsafe, say what approval is needed."
            )
            step.status = "completed"
            self.tasks.save(run)

        run.final_answer = self.ask(
            f"Summarize the completed task for the user.\nGoal: {goal}\n"
            f"Steps and results: {json.dumps([step.__dict__ for step in run.steps], ensure_ascii=True)}"
        )
        run.status = "completed"
        self.tasks.save(run)
        self.events.write("task_completed", f"{run.id}: {goal}")
        return run

    def _maybe_use_tool(self, goal: str, step: str) -> str:
        prompt = f"""Available tools: {', '.join(self.tools.names())}.
Choose at most one tool for this step. Return JSON only:
{{"tool": "none", "argument": ""}}

Use browse only with a URL. Use screen_ocr only when the step needs current screen text.
Use shell only when the user clearly wants local command execution.

Goal: {goal}
Step: {step}
"""
        raw = self.llm.chat([{"role": "user", "content": prompt}], mode="fast")
        try:
            data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        except Exception:
            return ""
        tool = data.get("tool", "none")
        argument = data.get("argument", "")
        if tool in {"", "none", None}:
            return ""
        result = self.tools.run(str(tool), str(argument))
        self.events.write("tool_used", f"{tool}: {argument}")
        return result[:8000]
