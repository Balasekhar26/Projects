from __future__ import annotations

import httpx
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.core.capability_ladder import build_capability_ladder
from backend.core.builder_brain import builder_profile, workspace_map
from backend.core.cluster_plan import cluster_plan
from backend.core.config import load_config
from backend.core.free_tool_catalog import free_tool_decision_report
from backend.core.free_stack import free_stack_report
from backend.core.hardware_requirements import hardware_requirements
from backend.core.installer import (
    request_missing_install_approval,
    run_approved_install_job,
)
from backend.core.logger import read_log
from backend.core.memory import build_memory_context, memory, recall, remember
from backend.core.model_router import available_models, health
from backend.ai_engine.model_router import local_model_profiles
from backend.labs.airllm_lab.adapter import (
    AirLLMRequest as AirLLMGeneration,
    airllm_status,
    generate_with_airllm,
)
from backend.labs.simulation_lab.mirofish_adapter import run_simulation, simulation_status
from backend.core.operator import build_operator_plan
from backend.core.platform_support import platform_support_report
from backend.core.project_indexer import build_project_index, search_project_index
from backend.core.project_blueprint import project_ecosystem
from backend.core.self_evolution import run_self_evolution_cycle
from backend.core.source_policy import source_first_policy
from backend.core.task_resume import resume_long_task
from backend.core.tool_adoption import (
    continue_tool_adoption_for_approval,
    list_tool_adoptions,
    request_tool_adoption,
)
from backend.core.tool_scout import scout_for_task, scout_status
from backend.tools.finance_brain import (
    compare_forecasts,
    forecast_ohlcv,
    kronos_status,
    load_ohlcv_csv,
)
from backend.tools.web_research.website_extractor import extract_website
from backend.tools.writing.grammar_api import check_grammar, writing_status
from backend.tools.writing.rewrite_helper import improve_text


def _run_graph(message: str) -> dict[str, object]:
    from backend.core.graph import run_graph

    return run_graph(message)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatSessionRequest(BaseModel):
    title: str = "New chat"


class ChatMessageRequest(BaseModel):
    role: str
    content: str
    agent: str = ""
    risk: str = ""
    metadata: str = "{}"


class MemoryRequest(BaseModel):
    text: str
    category: str = "general"


class LongTaskRequest(BaseModel):
    title: str
    goal: str
    priority: str = "normal"
    source_session_id: str = ""


class LongTaskUpdateRequest(BaseModel):
    status: str | None = None
    progress: str | None = None
    next_step: str | None = None


class ApprovalDecision(BaseModel):
    status: str


class ImprovementRequest(BaseModel):
    title: str
    motive: str
    proposal: str
    risk: str = "medium"


class ImprovementDecision(BaseModel):
    status: str


class SkillRequest(BaseModel):
    name: str
    trigger: str
    steps: str
    tools: str = ""
    risk: str = "low"
    trust: str = "draft"


class SkillTrustDecision(BaseModel):
    trust: str


class SkillResultRequest(BaseModel):
    success: bool
    reflection: str = ""


class ReflectionRequest(BaseModel):
    task: str
    outcome: str
    lesson: str
    skill_id: str | None = None


class SkillEvaluationRequest(BaseModel):
    skill_id: str
    result: str
    score: int
    notes: str


class OperatorPlanRequest(BaseModel):
    message: str


class ToolScoutRequest(BaseModel):
    task: str
    outcome: str = ""


class WritingCheckRequest(BaseModel):
    text: str


class WritingRewriteRequest(BaseModel):
    text: str
    tone: str = "clear"


class WebsiteExtractRequest(BaseModel):
    url: str
    goal: str = "Extract the main useful facts as structured data."
    use_scrapegraph: bool = False
    local_model: str = "gemma"


class SimulationRequest(BaseModel):
    seed: str
    horizon: str = "short"


class AirLLMGenerateRequest(BaseModel):
    prompt: str
    model_id: str = "garage-bAInd/Platypus2-70B-instruct"
    max_new_tokens: int = 80
    compression: str | None = "4bit"


class OhlcvCandle(BaseModel):
    timestamp: str | None = None
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    amount: float | None = None


class FinanceForecastRequest(BaseModel):
    candles: list[OhlcvCandle]
    horizon: int = 5
    use_kronos: bool = False


class FinanceCsvForecastRequest(BaseModel):
    path: str
    horizon: int = 5
    use_kronos: bool = False


app = FastAPI(title="Sekhar AI OS Backend", version="10.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, object]:
    ok, message = health()
    config = load_config()
    return {
        "status": "Sekhar AI OS backend running",
        "ollama_ok": ok,
        "ollama_message": message,
        "models": available_models(),
        "memory_count": memory.count(),
        "workspace": str(config.workspace_dir),
    }


@app.get("/ready")
def ready_check() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/free-stack")
def free_stack() -> dict[str, object]:
    return free_stack_report()


@app.get("/free-tools")
def free_tools() -> dict[str, object]:
    return free_tool_decision_report()


@app.get("/ai-engine/local-models")
def ai_engine_local_models() -> dict[str, object]:
    return local_model_profiles()


@app.get("/ai-engine/airllm/status")
def ai_engine_airllm_status() -> dict[str, object]:
    return airllm_status()


@app.post("/ai-engine/airllm/generate")
def ai_engine_airllm_generate(request: AirLLMGenerateRequest) -> dict[str, object]:
    try:
        return generate_with_airllm(
            AirLLMGeneration(
                prompt=request.prompt,
                model_id=request.model_id,
                max_new_tokens=request.max_new_tokens,
                compression=request.compression,
            )
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/writing/status")
def writing_engine_status() -> dict[str, object]:
    return writing_status()


@app.post("/writing/check")
def writing_check(request: WritingCheckRequest) -> dict[str, object]:
    return check_grammar(request.text)


@app.post("/writing/rewrite")
def writing_rewrite(request: WritingRewriteRequest) -> dict[str, object]:
    return improve_text(request.text, tone=request.tone)


@app.post("/web-research/extract")
def web_research_extract(request: WebsiteExtractRequest) -> dict[str, object]:
    try:
        return extract_website(
            request.url,
            request.goal,
            use_scrapegraph=request.use_scrapegraph,
            local_model=request.local_model,
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/simulation/status")
def simulation_lab_status() -> dict[str, object]:
    return simulation_status()


@app.post("/simulation/run")
def simulation_lab_run(request: SimulationRequest) -> dict[str, object]:
    return run_simulation(request.seed, request.horizon)


@app.get("/system/hardware-requirements")
def system_hardware_requirements() -> dict[str, object]:
    return hardware_requirements()


@app.get("/system/platform-support")
def system_platform_support() -> dict[str, object]:
    return platform_support_report()


@app.get("/cluster/plan")
def universal_ai_cluster_plan() -> dict[str, object]:
    return cluster_plan()


@app.get("/finance/kronos/status")
def finance_kronos_status() -> dict[str, object]:
    return kronos_status()


@app.post("/finance/forecast")
def finance_forecast(request: FinanceForecastRequest) -> dict[str, object]:
    candles = [candle.model_dump() for candle in request.candles]
    try:
        return forecast_ohlcv(
            candles, horizon=request.horizon, use_kronos=request.use_kronos
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/finance/forecast-csv")
def finance_forecast_csv(request: FinanceCsvForecastRequest) -> dict[str, object]:
    try:
        candles = load_ohlcv_csv(request.path)
        return forecast_ohlcv(
            candles, horizon=request.horizon, use_kronos=request.use_kronos
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/finance/compare")
def finance_compare(request: FinanceForecastRequest) -> dict[str, object]:
    candles = [candle.model_dump() for candle in request.candles]
    try:
        return compare_forecasts(candles, horizon=request.horizon)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/finance/compare-csv")
def finance_compare_csv(request: FinanceCsvForecastRequest) -> dict[str, object]:
    try:
        candles = load_ohlcv_csv(request.path)
        return compare_forecasts(candles, horizon=request.horizon)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/source-policy")
def source_policy() -> dict[str, object]:
    return source_first_policy()


@app.get("/tool-scout")
def tool_scout(limit: int = 25) -> dict[str, object]:
    return scout_status(limit=limit)


@app.post("/tool-scout/run")
def run_tool_scout(request: ToolScoutRequest) -> dict[str, object]:
    return scout_for_task(request.task, request.outcome)


@app.post("/tool-scout/{report_id}/adopt")
def adopt_tool_scout_report(report_id: str) -> dict[str, object]:
    result = request_tool_adoption(report_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Tool scout report not found")
    return result


@app.get("/tool-adoptions")
def tool_adoptions(limit: int = 25) -> dict[str, object]:
    return list_tool_adoptions(limit=limit)


@app.post("/tool-adoptions/approved/{approval_id}")
def continue_tool_adoption(approval_id: str) -> dict[str, object]:
    return continue_tool_adoption_for_approval(approval_id)


@app.post("/install/missing/request")
def request_missing_installs() -> dict[str, object]:
    return request_missing_install_approval()


@app.post("/install/approved/{approval_id}")
def run_approved_installs(approval_id: str) -> dict[str, object]:
    return run_approved_install_job(approval_id)


@app.get("/capability-ladder")
def capability_ladder() -> dict[str, object]:
    return build_capability_ladder()


@app.get("/builder/profile")
def get_builder_profile() -> dict[str, object]:
    return builder_profile()


@app.get("/builder/workspace-map")
def get_workspace_map(limit: int = 80) -> dict[str, object]:
    return workspace_map(limit=limit)


@app.get("/project-index")
def project_index(limit: int = 220) -> dict[str, object]:
    return build_project_index(limit=limit)


@app.get("/project-index/search")
def project_index_search(q: str, limit: int = 30) -> dict[str, object]:
    return search_project_index(q, limit=limit)


@app.get("/projects/ecosystem")
def get_project_ecosystem() -> dict[str, object]:
    return project_ecosystem()


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, object]:
    if request.session_id:
        memory.add_chat_message(
            request.session_id, "user", _strip_operator_prefix(request.message)
        )
    state = _run_graph(request.message)
    if request.session_id:
        memory.add_chat_message(
            request.session_id,
            "assistant",
            str(state.get("result") or ""),
            agent=str(state.get("selected_agent") or ""),
            risk=str(state.get("risk_level") or ""),
        )
    return {"response": state.get("result"), "state": state}


@app.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "system", "content": "Sekhar AI OS connected."})
    while True:
        user_message = await websocket.receive_text()
        await websocket.send_json(
            {"type": "progress", "content": "Planning and routing..."}
        )
        state = _run_graph(user_message)
        for line in state.get("logs", []):
            await websocket.send_json({"type": "progress", "content": line})
        await websocket.send_json(
            {
                "type": "assistant",
                "content": state.get("result") or "",
                "approval_required": state.get("approval_required", False),
                "approval_id": state.get("approval_id"),
                "risk_level": state.get("risk_level", "unknown"),
                "selected_agent": state.get("selected_agent"),
                "routing": (
                    state.get("tool_request", {}).get("agent_routing")
                    if state.get("tool_request")
                    else None
                ),
                "operator_plan": state.get("operator_plan"),
            }
        )


@app.post("/memory")
def add_memory(request: MemoryRequest) -> dict[str, str]:
    return {"id": remember(request.text, category=request.category)}


@app.post("/chat-sessions")
def create_chat_session(request: ChatSessionRequest) -> dict[str, object]:
    return {"item": memory.create_chat_session(request.title)}


@app.get("/chat-sessions")
def chat_sessions(limit: int = 50) -> dict[str, object]:
    return {"items": memory.list_chat_sessions(limit=limit)}


@app.get("/chat-sessions/{session_id}")
def get_chat_session(session_id: str) -> dict[str, object]:
    item = memory.get_chat_session(session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"item": item, "messages": memory.list_chat_messages(session_id)}


@app.post("/chat-sessions/{session_id}/messages")
def add_chat_session_message(
    session_id: str, request: ChatMessageRequest
) -> dict[str, object]:
    try:
        item = memory.add_chat_message(
            session_id=session_id,
            role=request.role,
            content=request.content,
            agent=request.agent,
            risk=request.risk,
            metadata=request.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@app.get("/memory/search")
def search_memory(q: str, limit: int = 5) -> dict[str, object]:
    return {"items": recall(q, n_results=limit)}


@app.get("/memory/context")
def memory_context(q: str) -> dict[str, object]:
    return {"context": build_memory_context(q)}


@app.post("/long-tasks")
def create_long_task(request: LongTaskRequest) -> dict[str, object]:
    try:
        item = memory.create_long_task(
            title=request.title,
            goal=request.goal,
            priority=request.priority,
            source_session_id=request.source_session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@app.get("/long-tasks")
def long_tasks(status: str | None = None, limit: int = 25) -> dict[str, object]:
    return {"items": memory.list_long_tasks(status=status, limit=limit)}


@app.get("/long-tasks/search")
def search_long_tasks(q: str, limit: int = 5) -> dict[str, object]:
    return {"items": memory.find_relevant_long_tasks(q, limit=limit)}


@app.post("/long-tasks/{task_id}")
def update_long_task(task_id: str, request: LongTaskUpdateRequest) -> dict[str, object]:
    try:
        item = memory.update_long_task(
            task_id,
            status=request.status,
            progress=request.progress,
            next_step=request.next_step,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Long task not found")
    return {"item": item}


@app.post("/long-tasks/{task_id}/resume")
def resume_task(task_id: str) -> dict[str, object]:
    result = resume_long_task(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Long task not found")
    return result


@app.post("/operator/plan")
def operator_plan(request: OperatorPlanRequest) -> dict[str, object]:
    return {"plan": build_operator_plan(request.message, selected_agent=None)}


@app.get("/approvals")
def approvals(status: str | None = "pending", limit: int = 25) -> dict[str, object]:
    return {"items": memory.list_approvals(status=status, limit=limit)}


@app.post("/approvals/{approval_id}")
def decide_approval(approval_id: str, decision: ApprovalDecision) -> dict[str, object]:
    try:
        item = memory.update_approval(approval_id, decision.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return {"item": item}


@app.get("/improvements")
def improvements(status: str | None = None, limit: int = 25) -> dict[str, object]:
    return {"items": memory.list_improvements(status=status, limit=limit)}


@app.post("/improvements")
def create_improvement(request: ImprovementRequest) -> dict[str, object]:
    try:
        improvement_id = memory.create_improvement(
            title=request.title,
            motive=request.motive,
            proposal=request.proposal,
            risk=request.risk,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    item = memory.update_improvement(improvement_id, "pending")
    return {"item": item}


@app.post("/improvements/{improvement_id}")
def decide_improvement(
    improvement_id: str, decision: ImprovementDecision
) -> dict[str, object]:
    try:
        item = memory.update_improvement(improvement_id, decision.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Improvement proposal not found")
    return {"item": item}


@app.get("/skills")
def skills(trust: str | None = None, limit: int = 50) -> dict[str, object]:
    return {"items": memory.list_skills(trust=trust, limit=limit)}


@app.post("/skills")
def create_skill(request: SkillRequest) -> dict[str, object]:
    try:
        skill_id = memory.create_skill(
            name=request.name,
            trigger=request.trigger,
            steps=request.steps,
            tools=request.tools,
            risk=request.risk,
            trust=request.trust,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": memory.get_skill(skill_id)}


@app.post("/skills/{skill_id}/trust")
def update_skill_trust(
    skill_id: str, decision: SkillTrustDecision
) -> dict[str, object]:
    try:
        item = memory.update_skill_trust(skill_id, decision.trust)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"item": item}


@app.post("/skills/{skill_id}/result")
def record_skill_result(
    skill_id: str, request: SkillResultRequest
) -> dict[str, object]:
    item = memory.record_skill_result(
        skill_id, success=request.success, reflection=request.reflection
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    memory.create_reflection(
        task=f"Skill result: {item['name']}",
        outcome="success" if request.success else "failure",
        lesson=request.reflection or "No reflection supplied.",
        skill_id=skill_id,
    )
    return {"item": item}


@app.get("/reflections")
def reflections(
    outcome: str | None = None, skill_id: str | None = None, limit: int = 50
) -> dict[str, object]:
    return {
        "items": memory.list_reflections(
            outcome=outcome, skill_id=skill_id, limit=limit
        )
    }


@app.post("/reflections")
def create_reflection(request: ReflectionRequest) -> dict[str, object]:
    try:
        reflection_id = memory.create_reflection(
            task=request.task,
            outcome=request.outcome,
            lesson=request.lesson,
            skill_id=request.skill_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": reflection_id}


@app.get("/skill-evaluations")
def skill_evaluations(
    skill_id: str | None = None, limit: int = 50
) -> dict[str, object]:
    return {"items": memory.list_skill_evaluations(skill_id=skill_id, limit=limit)}


@app.post("/skill-evaluations")
def create_skill_evaluation(request: SkillEvaluationRequest) -> dict[str, object]:
    try:
        evaluation_id = memory.create_skill_evaluation(
            skill_id=request.skill_id,
            result=request.result,
            score=request.score,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": evaluation_id}


@app.post("/self-evolution/run")
def self_evolution_run(limit: int = 25) -> dict[str, object]:
    return run_self_evolution_cycle(limit=limit)


@app.get("/logs")
def logs(limit: int = 100) -> dict[str, object]:
    return {"lines": read_log(limit=limit)}


def _strip_operator_prefix(message: str) -> str:
    lines = message.splitlines()
    if lines and lines[0].startswith("[operator mode:"):
        return "\n".join(lines[1:]).strip()
    return message
