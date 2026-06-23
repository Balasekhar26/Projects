from __future__ import annotations

from langgraph.graph import END, StateGraph

from backend.agents.browser import browser_node
from backend.agents.builder import builder_node
from backend.agents.coder import coder_node
from backend.agents.desktop import desktop_node
from backend.agents.evaluator import evaluator_node
from backend.agents.file_agent import file_node
from backend.agents.finance import finance_node
from backend.agents.memory_agent import memory_node
from backend.agents.planner import planner_node
from backend.agents.researcher import researcher_node
from backend.agents.safety_agent import safety_node
from backend.agents.self_improver import self_improver_node
from backend.agents.terminal import terminal_node
from backend.agents.vision import vision_node
from backend.agents.voice import voice_node
from backend.agents.monitoring import monitoring_node
from backend.core.logger import log_event
from backend.core.state import AgentState


def route_agent(state: AgentState) -> str:
    if state.get("approval_required") and state.get("result"):
        return "evaluator"
    selected = state.get("selected_agent") or "evaluator"
    return (
        selected
        if selected
        in {
            "coder",
            "builder",
            "browser",
            "desktop",
            "researcher",
            "vision",
            "voice",
            "file",
            "terminal",
            "finance",
            "self_improver",
            "monitoring",
        }
        else "evaluator"
    )


def route_evaluator(state: AgentState) -> str:
    if state.get("selected_agent") and state.get("result") is None:
        return "safety"
    return "end"



def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("memory", memory_node)
    graph.add_node("planner", planner_node)
    graph.add_node("safety", safety_node)
    graph.add_node("coder", coder_node)
    graph.add_node("builder", builder_node)
    graph.add_node("browser", browser_node)
    graph.add_node("desktop", desktop_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("vision", vision_node)
    graph.add_node("voice", voice_node)
    graph.add_node("file", file_node)
    graph.add_node("terminal", terminal_node)
    graph.add_node("finance", finance_node)
    graph.add_node("self_improver", self_improver_node)
    graph.add_node("monitoring", monitoring_node)
    graph.add_node("evaluator", evaluator_node)

    graph.set_entry_point("memory")
    graph.add_edge("memory", "planner")
    graph.add_edge("planner", "safety")
    graph.add_conditional_edges(
        "safety",
        route_agent,
        {
            "coder": "coder",
            "builder": "builder",
            "browser": "browser",
            "desktop": "desktop",
            "researcher": "researcher",
            "vision": "vision",
            "voice": "voice",
            "file": "file",
            "terminal": "terminal",
            "finance": "finance",
            "self_improver": "self_improver",
            "monitoring": "monitoring",
            "evaluator": "evaluator",
        },
    )
    for node in [
        "coder",
        "builder",
        "browser",
        "desktop",
        "researcher",
        "vision",
        "voice",
        "file",
        "terminal",
        "finance",
        "self_improver",
        "monitoring",
    ]:
        graph.add_edge(node, "evaluator")
    graph.add_conditional_edges(
        "evaluator",
        route_evaluator,
        {
            "safety": "safety",
            "end": END,
        },
    )
    return graph.compile()



compiled_graph = build_graph()


def run_graph(
    user_input: str,
    approved_approval_id: str | None = None,
    chat_session_id: str | None = None,
    current_chat_message_id: str | None = None,
    memory_query: str | None = None,
    ephemeral_worker: bool = False,
    trust_tag: str = "SYSTEM_TRUST",
) -> AgentState:
    state: AgentState = {
        "user_input": user_input,
        "memory_query": memory_query,
        "chat_session_id": chat_session_id,
        "current_chat_message_id": current_chat_message_id,
        "ephemeral_worker": ephemeral_worker,
        "plan": None,
        "selected_agent": None,
        "memory_context": None,
        "related_messages": [],
        "approval_id": None,
        "approved_approval_id": approved_approval_id,
        "approved": approved_approval_id is not None,
        "approval_required": False,
        "risk_level": "unknown",
        "result": None,
        "logs": [],
        "operator_plan": None,
        "trust_tag": trust_tag,
    }
    from backend.core.rbil import RBIL
    rbil_res = RBIL.process(user_input)
    if rbil_res:
        state.update(rbil_res)
        log_event(
            f"rbil_hit request={user_input!r} agent={state.get('selected_agent')}"
        )
        return state

    result = compiled_graph.invoke(state)
    log_event(
        f"request={user_input!r} agent={result.get('selected_agent')} risk={result.get('risk_level')}"
    )
    return result
