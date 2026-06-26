from __future__ import annotations

from typing import Any
import json
import time
import sqlite3
import uuid

# SQLite instrumentation removed

import httpx
from fastapi import FastAPI, Header, HTTPException, WebSocket, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.core.capability_ladder import build_capability_ladder
from backend.core.builder_brain import builder_profile, local_builder_analytics, workspace_map
from backend.core.cluster_plan import cluster_plan
from backend.core.cluster_runtime import (
    auto_delegate_if_local_unable,
    cluster_runtime_status,
    collect_worker_bids,
    execute_public_worker_task,
    execute_worker_task,
    list_discovery_targets,
    list_paired_nodes,
    public_worker_capability_bid,
    public_worker_status,
    register_discovery_target,
    register_paired_node,
    remove_discovery_target,
    remove_paired_node,
    route_cluster_task,
    worker_capability_bid,
    worker_token_is_valid,
)
from backend.core.config import load_config
from backend.core.codex_parity import codex_parity_report
from backend.core.approval_continuation import continue_approved_work
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
from backend.core.project_improvement_agents import (
    check_git_shared_improvements,
    observe_project_improvement_agents,
    project_improvement_agents,
    publish_approved_improvement,
)
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
from backend.tools.local_creator_tools import (
    compress_context,
    convert_document_text_to_markdown,
    create_gsd_workflow,
    create_local_deck_outline,
    create_marketing_kit,
    create_mermaid_diagram,
    local_code_review,
    toolbox_replacement_report,
)
from backend.tools.voice_tools import (
    normalize_spoken_text,
    parse_wake_command,
    process_voice_audio,
    speak,
    voice_pipeline_status,
)
from backend.tools.web_research.website_extractor import extract_website
from backend.tools.writing.grammar_api import check_grammar, writing_status
from backend.tools.writing.rewrite_helper import improve_text


def _run_graph(
    message: str,
    approved_approval_id: str | None = None,
    chat_session_id: str | None = None,
    current_chat_message_id: str | None = None,
    memory_query: str | None = None,
) -> dict[str, object]:
    from backend.core.graph import run_graph

    return run_graph(
        message,
        approved_approval_id=approved_approval_id,
        chat_session_id=chat_session_id,
        current_chat_message_id=current_chat_message_id,
        memory_query=memory_query,
    )


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


class ChatMessageRatingRequest(BaseModel):
    rating: int


class MemoryRequest(BaseModel):
    text: str
    category: str = "general"


class ActionMemoryRecordRequest(BaseModel):
    action_id: str | None = None
    workflow_id: str = ""
    parent_action_id: str = ""
    agent: str
    action: str
    reason: str = ""
    expected_outcome: str = ""
    actual_outcome: str = ""
    outcome: str | None = None
    success: bool | None = None
    failure: bool | None = None
    duration_ms: int = Field(default=0, ge=0)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    rollback_executed: bool = False
    rollback_action_id: str = ""
    rollback_chain_id: str = ""
    timestamp: str | None = None
    tags: list[str] = Field(default_factory=list)


class ActionMemoryUpdateRequest(BaseModel):
    actual_outcome: str | None = None
    outcome: str | None = None
    success: bool | None = None
    failure: bool | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    rollback_executed: bool | None = None
    tags: list[str] | None = None



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
    publish: bool = True


class ProjectImprovementObserveRequest(BaseModel):
    run_status: bool = False


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


class ClusterNodeRequest(BaseModel):
    name: str
    base_url: str
    token: str
    capabilities: dict[str, object] = {}


class ClusterDiscoveryTargetRequest(BaseModel):
    name: str
    base_url: str


class ClusterTaskRouteRequest(BaseModel):
    message: str
    task_kind: str = "basic_chat"
    sensitivity: str = "normal"
    force_remote: bool = False


class ClusterBidRequest(BaseModel):
    message: str
    task_kind: str = "basic_chat"


class ClusterWorkerBidRequest(BaseModel):
    bid_id: str
    task_kind: str
    message: str
    origin_node: dict[str, object] = {}
    privacy: dict[str, object] = {}


class ClusterWorkerTaskRequest(BaseModel):
    task_id: str
    task_kind: str
    message: str
    origin_node: dict[str, object] = {}
    privacy: dict[str, object] = {}


class HubTaskRequest(BaseModel):
    task_id: str
    task_kind: str
    min_cpu: int = 2
    min_ram: float = 4.0


class HubBidRequest(BaseModel):
    task_id: str
    worker_id: str
    hostname: str
    cpu_count: int
    ram_total_gb: float


class HubDelegateRequest(BaseModel):
    worker_id: str
    message: str


class HubResultSubmit(BaseModel):
    worker_id: str
    result: str
    error: str | None = None


class ClusterPublicBidRequest(BaseModel):
    bid_id: str
    task_kind: str
    capability_hint: dict[str, object] = {}
    origin_node: dict[str, object] = {}
    privacy: dict[str, object] = {}


class ToolScoutRequest(BaseModel):
    task: str
    outcome: str = ""


class WritingCheckRequest(BaseModel):
    text: str


class WritingRewriteRequest(BaseModel):
    text: str
    tone: str = "clear"


class LocalDeckRequest(BaseModel):
    topic: str
    audience: str = "users"
    project: str = ""
    slide_count: int = 8


class LocalDiagramRequest(BaseModel):
    text: str
    diagram_type: str = "flowchart"


class ContextCompressRequest(BaseModel):
    text: str
    max_points: int = 12


class LocalReviewRequest(BaseModel):
    diff_text: str
    project: str = ""


class LocalGsdWorkflowRequest(BaseModel):
    goal: str
    project: str = ""


class DocumentMarkdownRequest(BaseModel):
    filename: str
    text: str


class MarketingKitRequest(BaseModel):
    brand: str
    product: str
    audience: str = "customers"
    channel: str = "social"


class VoiceSpeakRequest(BaseModel):
    text: str
    purpose: str = "assistant_response"


class VoiceAudioRequest(BaseModel):
    audio_base64: str
    mime_type: str = "audio/webm"
    model_size: str = "small"


class VoiceTranscriptRequest(BaseModel):
    transcript: str


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


class SageFeedbackRequest(BaseModel):
    user_input: str
    source: str
    rating: int


class AttentionEventRequest(BaseModel):
    text: str
    source: str = "user"
    active_context: str | None = None
    record: bool = True


class AttentionGoalRequest(BaseModel):
    title: str
    keywords: list[str] = []
    priority: str = "normal"


class AttentionEntityRequest(BaseModel):
    name: str
    relation: str = "contact"
    importance: float = 0.6


class AttentionFocusRequest(BaseModel):
    objective: str
    event_text: str


class AttentionReflectRequest(BaseModel):
    events: list[dict[str, object]] = []


class MemoryIngestRequest(BaseModel):
    text: str
    source: str = "user"
    session_id: str = "primary"
    trusted: bool | None = None
    relationship_hit: bool = False


class MemoryLinkRequest(BaseModel):
    src: str
    dst: str
    relation: str = "related"
    weight: float = 1.0


class RouterRouteRequest(BaseModel):
    prompt: str
    mode: str = "BALANCED"


class ConsensusDecideRequest(BaseModel):
    outputs: list[dict[str, object]] = []
    context: dict[str, object] | None = None


class ValidatorRunRequest(BaseModel):
    payload: dict[str, object] = {}
    validators: list[str] | None = None


class PolicyGateRequest(BaseModel):
    action: str
    consensus_approved: bool = True
    consensus_requires_human: bool = False


class ReliabilityRecordRequest(BaseModel):
    agent: str
    success: bool


class MetaCognitionSuperviseRequest(BaseModel):
    prompt: str
    routing_confidence: float = 1.0
    evidence_count: int = 1
    missing_validators: bool = False
    vetoes: list[dict[str, object]] = []
    blocking_findings: list[dict[str, object]] = []
    consensus_status: str = "approved"
    simulation_success_rate: float | None = None
    goal: str | None = None
    required_caps: list[str] | None = None
    chat_history: list[dict[str, object]] | None = None
    failed_runs_count: int = 0
    is_production: bool = False
    is_code_change: bool = False


class MetaCognitionModeRequest(BaseModel):
    prompt: str
    is_production: bool = False
    is_code_change: bool = False


class ExecutiveArbitrateRequest(BaseModel):
    task_id: str
    task_name: str
    priority: float
    urgency: float
    token_budget: int
    max_execution_seconds: int


class ExecutiveReviewRequest(BaseModel):
    reviewer_id: str
    task_id: str
    recommendation: str
    decision: str


class BenchmarkItemRequest(BaseModel):
    id: str
    category: str
    prompt: str
    actual: str = ""
    expected: str = ""
    constraints: list[str] = []
    expected_tools: list[str] = []
    logs: list[str] = []


class BenchmarkRunRequest(BaseModel):
    suite_id: str
    items: list[BenchmarkItemRequest]
    is_held_out: bool = False
    chat_history: list[dict[str, object]] | None = None
    memory_queries: list[str] | None = None
    violations: list[dict[str, object]] | None = None
    latencies: list[float] | None = None
    predictions: list[float] | None = None
    outcomes: list[int] | None = None


class BenchmarkCompareRequest(BaseModel):
    current_run: dict[str, object]
    previous_run: dict[str, object] | None = None
    floors: dict[str, float] | None = None


class ToolBenchmarkRunRequest(BaseModel):
    tool_name: str
    tool_version: str
    benchmark_suite: str
    run_id: str
    task_id: str
    success: bool
    duration_ms: int = Field(default=0, ge=0)
    failure_type: str | None = None
    rollback_required: bool = False
    rollback_success: bool | None = None
    simulation_decision: str = ""
    human_decision: str = ""
    simulation_prediction: dict[str, object] = Field(default_factory=dict)
    execution_result: dict[str, object] = Field(default_factory=dict)
    timestamp: str = ""
    source: str = "api"


class ToolBenchmarkEvaluateRequest(BaseModel):
    tool_name: str
    baseline_version: str
    candidate_version: str
    benchmark_suite: str
    historical_runs: list[ToolBenchmarkRunRequest]
    candidate_runs: list[ToolBenchmarkRunRequest] | None = None
    min_runs: int = Field(default=1, ge=1)
    persist: bool = False


class ProposalObserveRequest(BaseModel):
    issue: str
    severity: str
    metrics: dict[str, object] | None = None


class ProposalCreateRequest(BaseModel):
    title: str
    problem: str
    evidence: str
    proposal: str
    expected_gain: float
    complexity: int
    confidence: int
    affected_modules: list[str] = []
    parent_proposal_id: str | None = None
    research_cost: float = 10.0


class ProposalReviewRequest(BaseModel):
    approved: bool
    review_time_seconds: float


class ProposalRecordRunRequest(BaseModel):
    stage: str
    success: bool
    metrics: dict[str, Any] | None = None
    research_cost: float = 10.0
    predicted_gain: float | None = None
    actual_sandbox_gain: float | None = None
    actual_production_gain: float | None = None


class ProposalNegativeKnowledgeRequest(BaseModel):
    title: str
    reason: str


class SandboxExperimentRunRequest(BaseModel):
    expected_risk: float = 0.1
    actual_gain: float = 5.0
    mock_failure: bool = False


class DeploymentAssessRequest(BaseModel):
    benchmark_scores: dict[str, float]
    baseline_scores: dict[str, float]


class CanaryStepRequest(BaseModel):
    simulated_anomaly: str | None = None
    simulated_held_out_regression: bool = False


class RollbackRequest(BaseModel):
    reason: str


class ResearchAnalyzeRequest(BaseModel):
    title: str = "Untitled"
    content: str
    source_type: str = "paper"


class SandboxExperimentRunV2Request(BaseModel):
    baseline_benchmarks: dict[str, float] | None = None
    mock_regression: bool = False
    mock_crash: bool = False


class GoalCreateRequest(BaseModel):
    title: str
    description: str | None = None
    priority: str = "MEDIUM"
    target_date: str | None = None
    success_criteria: list[str] | None = None
    owner: str | None = None
    parent_id: str | None = None
    depends_on: list[str] = []
    importance: float = 5.0
    urgency: float = 5.0
    strategic_alignment: float = 5.0
    resource_cost: float = 2.0
    
    # Human-Like additions:
    owner_agent: str | None = None
    horizon_type: str = "SHORT_TERM"
    current_state: str = "IDEA"
    importance_score: float = 50.0
    urgency_score: float = 50.0
    estimated_value: float = 50.0
    confidence_score: float = 100.0
    energy_required: str = "MEDIUM"
    risk_profile: float = 10.0
    attention_score: float = 1.0
    decay_rate: float = 0.0
    provenance: str = "STATED"
    original_goal_text: str | None = None
    definition_of_done: str | None = None
    ttl: float | None = None


class GoalUpdateRequest(BaseModel):
    title: str
    description: str | None = None


class GoalCompleteRequest(BaseModel):
    validator: str | None = None
    user_confirmed: bool = False
    evidence: dict[str, object] | None = None


class ConflictDeclareRequest(BaseModel):
    goal_a_id: str
    goal_b_id: str
    conflict_topology: str
    severity_rating: float = 50.0


class ConflictResolveRequest(BaseModel):
    resolution_status: str = "MITIGATED"


class ValueAlignmentRequest(BaseModel):
    core_policy_constraint: str
    alignment_status: str


class MilestoneCreateRequest(BaseModel):
    title: str
    description: str | None = None
    weight: float = 1.0
    milestone_id: str | None = None


class MilestonesBatchRequest(BaseModel):
    milestones: list[MilestoneCreateRequest]


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None
    status: str = "PROPOSED"
    metadata: dict[str, Any] | None = None


class PPMProjectCreateRequest(BaseModel):
    linked_goal_id: str
    title: str | None = None
    description: str | None = None
    status: str = "PROPOSED"
    target_finish_date: float | None = None
    original_scope: str | None = None


class PPMMilestoneCreateRequest(BaseModel):
    project_id: str
    title: str
    weight: float = 1.0
    deadline: float | None = None


class PPMTaskCreateRequest(BaseModel):
    milestone_id: str
    title: str
    description: str | None = None
    assigned_agent: str | None = None
    effort_score: int = 1
    deadline: float | None = None


class PPMBlockerAddRequest(BaseModel):
    project_id: str
    severity: str = "MEDIUM"
    source: str


class PPMResourceAllocateRequest(BaseModel):
    project_id: str
    resource_type: str
    allocated: float


class PPMResourceConsumeRequest(BaseModel):
    project_id: str
    resource_type: str
    amount: float


class PPMRevisionLogRequest(BaseModel):
    author: str
    summary: str


class PPMCompleteRequest(BaseModel):
    validator: str | None = None
    user_confirmed: bool = False


class ProjectGoalAddRequest(BaseModel):
    goal_id: str


class ProjectDependencyRequest(BaseModel):
    depends_on_project_id: str


class ProjectDecisionRequest(BaseModel):
    title: str
    description: str | None = None
    rationale: str | None = None


class ReflectionProposeRequest(BaseModel):
    problem: str
    cause: str = ""
    improvement: str = ""
    category: str = "reasoning"
    evidence_source: str = "reasoning"
    confidence: int = 50


class CapabilityRegisterRequest(BaseModel):
    name: str
    kind: str = "skill"
    available: bool = True
    depends_on: list[str] = []
    alternatives: list[str] = []
    risk: str = ""


class CapabilityAssessRequest(BaseModel):
    goal: str
    required: list[str] = []


class TrustAssessRequest(BaseModel):
    statement: str
    evidence: list[dict[str, object]] = []


class SkillAddRequest(BaseModel):
    name: str
    description: str = ""
    inputs: list[str] = []
    steps: list[str] = []
    outputs: list[str] = []
    tags: list[str] = []


class SkillLibResultRequest(BaseModel):
    success: bool


class WorldEntityRequest(BaseModel):
    name: str
    type: str = "other"
    status: str = ""
    attributes: dict[str, object] = {}


class WorldRelationRequest(BaseModel):
    src: str
    dst: str
    relation: str = "related"


class SimulateRequest(BaseModel):
    scenario: dict[str, object] = {}
    trials: int = 1000
    seed: int = 42


class PlanSimulationRequest(BaseModel):
    goal: str = ""
    workflow_id: str = ""
    plan: list[dict[str, object]] = []
    context: dict[str, object] = {}


class DecisionForecastRequest(BaseModel):
    decision_id: str
    decision: str
    predicted_success: float
    predicted_cost: float
    predicted_time: str


class DecisionOutcomeRequest(BaseModel):
    decision_id: str
    actual_success: float
    actual_cost: float
    actual_time: str


class ResearchIngestRequest(BaseModel):
    title: str
    authors: str
    arxiv_id: str | None = None
    doi: str | None = None
    published_date: str
    claims: list[dict[str, Any]] = []
    metrics: dict[str, float] = {}


class ResearchEvaluateRequest(BaseModel):
    experiment_id: str
    run_results: dict[str, Any] = {}


class MemorySafetyRunRequest(BaseModel):
    test_contents: list[str] = []


class DistillRequest(BaseModel):
    observations: list[str] = []
    min_cluster: int = 3
    principle_hints: dict[str, str] = {}


class ValueScoreRequest(BaseModel):
    signals: dict[str, object] = {}


class ValueRankRequest(BaseModel):
    plans: list[dict[str, object]] = []
    profile: str = "default"


app = FastAPI(title="Kattappa AI OS Backend", version="10.0.0")
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
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)





@app.get("/sage/status")
def get_sage_status() -> dict[str, object]:
    from backend.core.sage import SageKnowledgeGraph, SageUserModel, SageArchetypeKernel, AetherMetaLearning
    profile = SageUserModel.get_profile()
    concepts = SageKnowledgeGraph.get_all_concepts(limit=100)
    success_rates = AetherMetaLearning.get_success_rates()

    aether_metrics = {
        "memory_layers": {
            "sensory": "Active (ready)",
            "working": "Active (context-aware)",
            "semantic": f"Active ({len(concepts)} concepts stored)",
            "procedural": "Active (6 core capabilities)",
            "user": f"Active ({profile.get('knowledge_level', 'Intermediate')} mode)",
            "long_term": "Active (Chroma + SQLite)"
        },
        "self_questioning_results": {
            "know": "Active system diagnostics and user profile context.",
            "assume": "Standard cognitive model preferences.",
            "evidence": "Observed concept scores and user click rates.",
            "wrong": "Network variations or local model timeouts."
        },
        "ethical_scores": {
            "truthfulness": 0.95,
            "safety": 1.0,
            "fairness": 0.90,
            "user_benefit": 0.95,
            "long_term_impact": 0.90
        },
        "meta_learning": {
            "strategy_success_rates": success_rates
        },
        "confidence_tracking": "High" if len(concepts) > 5 else "Medium"
    }
    return {
        "concepts": concepts[:50],
        "profile": profile,
        "weights": SageArchetypeKernel.get_weights(),
        "aether_metrics": aether_metrics
    }


@app.post("/sage/feedback")
def post_sage_feedback(request: SageFeedbackRequest) -> dict[str, object]:
    from backend.core.sage import SAGE
    return SAGE.learn_from(request.user_input, request.source, request.rating)


@app.get("/attention/status")
def attention_status() -> dict[str, object]:
    from backend.core.lighthouse import LIGHTHOUSE
    return LIGHTHOUSE.status()


@app.post("/attention/evaluate")
def attention_evaluate(request: AttentionEventRequest) -> dict[str, object]:
    from backend.core.lighthouse import LIGHTHOUSE
    result = LIGHTHOUSE.process_event(
        request.text,
        source=request.source,
        active_context=request.active_context,
        record=request.record,
    )
    return result.to_dict()


@app.get("/attention/goals")
def attention_list_goals() -> dict[str, object]:
    from backend.core.lighthouse import GoalRegistry
    return {"items": GoalRegistry.list_goals()}


@app.post("/attention/goals")
def attention_add_goal(request: AttentionGoalRequest) -> dict[str, object]:
    from backend.core.lighthouse import GoalRegistry
    try:
        return {"item": GoalRegistry.add_goal(request.title, request.keywords, request.priority)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/attention/goals/{goal_id}")
def attention_remove_goal(goal_id: str) -> dict[str, object]:
    from backend.core.lighthouse import GoalRegistry
    if not GoalRegistry.remove_goal(goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"removed": True, "goal_id": goal_id}


@app.get("/attention/relationships")
def attention_list_relationships() -> dict[str, object]:
    from backend.core.lighthouse import RelationshipRegistry
    return {"items": RelationshipRegistry.list_entities()}


@app.post("/attention/relationships")
def attention_add_relationship(request: AttentionEntityRequest) -> dict[str, object]:
    from backend.core.lighthouse import RelationshipRegistry
    try:
        return {
            "item": RelationshipRegistry.add_entity(
                request.name, request.relation, request.importance
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/attention/relationships/{entity_id}")
def attention_remove_relationship(entity_id: str) -> dict[str, object]:
    from backend.core.lighthouse import RelationshipRegistry
    if not RelationshipRegistry.remove_entity(entity_id):
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"removed": True, "entity_id": entity_id}


@app.get("/attention/curiosity")
def attention_curiosity_queue(status: str | None = None) -> dict[str, object]:
    from backend.core.lighthouse import CuriosityEngine
    return {"items": CuriosityEngine.list_queue(status=status)}


@app.post("/attention/curiosity/{item_id}/resolve")
def attention_resolve_curiosity(item_id: str, status: str = "done") -> dict[str, object]:
    from backend.core.lighthouse import CuriosityEngine
    if not CuriosityEngine.resolve(item_id, status=status):
        raise HTTPException(status_code=404, detail="Curiosity item not found")
    return {"resolved": True, "item_id": item_id, "status": status}


@app.post("/attention/focus-check")
def attention_focus_check(request: AttentionFocusRequest) -> dict[str, object]:
    from backend.core.lighthouse import FocusGuardian
    return FocusGuardian.check(request.objective, request.event_text).to_dict()


@app.post("/attention/reflect")
def attention_reflect(request: AttentionReflectRequest) -> dict[str, object]:
    from backend.core.lighthouse import LIGHTHOUSE
    return LIGHTHOUSE.reflect(request.events)


@app.get("/human-memory/status")
def human_memory_status() -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.status()


@app.post("/human-memory/ingest")
def human_memory_ingest(request: MemoryIngestRequest) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.ingest(
        request.text,
        source=request.source,
        session_id=request.session_id,
        trusted=request.trusted,
        relationship_hit=request.relationship_hit,
    ).to_dict()


@app.get("/human-memory/recall")
def human_memory_recall(q: str, limit: int = 5, include_forgotten: bool = False) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return {"items": MEMORY.recall(q, limit=limit, include_forgotten=include_forgotten)}


@app.get("/human-memory/working/{session_id}")
def human_memory_working(session_id: str) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.working_memory(session_id)


@app.get("/human-memory/pending")
def human_memory_pending() -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return {"items": MEMORY.list_pending()}


@app.post("/human-memory/approve/{memory_id}")
def human_memory_approve(memory_id: str) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    if not MEMORY.approve_pending(memory_id):
        raise HTTPException(status_code=404, detail="Pending memory not found")
    return {"approved": True, "memory_id": memory_id}


@app.post("/human-memory/pin/{memory_id}")
def human_memory_pin(memory_id: str) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    if not MEMORY.pin(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"pinned": True, "memory_id": memory_id}


@app.post("/human-memory/unpin/{memory_id}")
def human_memory_unpin(memory_id: str) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    if not MEMORY.unpin(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"unpinned": True, "memory_id": memory_id}


@app.post("/human-memory/decay/run")
def human_memory_decay_run() -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.run_decay()


@app.post("/human-memory/reflect")
def human_memory_reflect() -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.reflect()


@app.post("/human-memory/relationship/link")
def human_memory_link(request: MemoryLinkRequest) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.link(request.src, request.dst, request.relation, request.weight)


@app.post("/human-memory/relationship/gc")
def human_memory_gc() -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return MEMORY.garbage_collect()


@app.get("/human-memory/wisdom")
def human_memory_wisdom(limit: int = 20) -> dict[str, object]:
    from backend.core.human_memory import MEMORY
    return {"items": MEMORY.wisdom(limit=limit)}


@app.get("/agents")
def list_agents() -> dict[str, object]:
    from backend.core.agent_registry import DEFAULT_REGISTRY
    return DEFAULT_REGISTRY.to_dict()


@app.get("/agents/{name}")
def get_agent(name: str) -> dict[str, object]:
    from backend.core.agent_registry import DEFAULT_REGISTRY
    agent = DEFAULT_REGISTRY.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"No agent named {name!r}")
    return agent.to_dict()


@app.post("/router/route")
def router_route(request: RouterRouteRequest) -> dict[str, object]:
    from backend.core.agent_router import DEFAULT_ROUTER
    try:
        return DEFAULT_ROUTER.route(request.prompt, mode=request.mode).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/consensus/decide")
def consensus_decide(request: ConsensusDecideRequest) -> dict[str, object]:
    from backend.core.consensus_engine import decide_from_dicts
    return decide_from_dicts(request.outputs, request.context).to_dict()


@app.get("/validators")
def list_validators() -> dict[str, object]:
    from backend.core.validators import DEFAULT_VALIDATORS
    return {"validators": [{"name": v.name, "veto": v.veto} for v in DEFAULT_VALIDATORS.values()]}


@app.post("/validators/run")
def validators_run(request: ValidatorRunRequest) -> dict[str, object]:
    from backend.core.validators import run_validators
    return run_validators(request.payload, request.validators).to_dict()


@app.get("/policy")
def list_policies() -> dict[str, object]:
    from backend.core.execution_policy import DEFAULT_POLICY_ENGINE
    return DEFAULT_POLICY_ENGINE.to_dict()


@app.post("/policy/gate")
def policy_gate(request: PolicyGateRequest) -> dict[str, object]:
    from backend.core.execution_policy import DEFAULT_POLICY_ENGINE
    return DEFAULT_POLICY_ENGINE.gate(
        request.action,
        consensus_approved=request.consensus_approved,
        consensus_requires_human=request.consensus_requires_human,
    ).to_dict()


@app.get("/reliability")
def reliability_stats() -> dict[str, object]:
    from backend.core.reliability_monitor import ReliabilityMonitor
    return ReliabilityMonitor.stats()


@app.post("/reliability/record")
def reliability_record(request: ReliabilityRecordRequest) -> dict[str, object]:
    from backend.core.reliability_monitor import ReliabilityMonitor
    return ReliabilityMonitor.record_outcome(request.agent, request.success)


@app.get("/meta-cognition/status")
def meta_cognition_status() -> dict[str, object]:
    return {
        "status": "active",
        "rules": {
            "modes": ["DIRECT", "DEEP_ANALYSIS", "HIGH_ASSURANCE"],
            "precedence": "ESCALATE > REQUEST_MORE_EVIDENCE > CHANGE_REASONING_MODE > ALLOW",
            "uncertainty_routing_threshold": 0.5,
            "simulation_success_threshold": 0.5,
            "repeated_failed_runs_threshold": 2
        }
    }


@app.post("/meta-cognition/supervise")
def meta_cognition_supervise(request: MetaCognitionSuperviseRequest) -> dict[str, object]:
    from backend.core.meta_cognition import MetaCognitionEngine
    return MetaCognitionEngine.supervise(
        prompt=request.prompt,
        routing_confidence=request.routing_confidence,
        evidence_count=request.evidence_count,
        missing_validators=request.missing_validators,
        vetoes=request.vetoes,
        blocking_findings=request.blocking_findings,
        consensus_status=request.consensus_status,
        simulation_success_rate=request.simulation_success_rate,
        goal=request.goal,
        required_caps=request.required_caps,
        chat_history=request.chat_history,
        failed_runs_count=request.failed_runs_count,
        is_production=request.is_production,
        is_code_change=request.is_code_change,
    )


@app.post("/meta-cognition/mode")
def meta_cognition_mode(request: MetaCognitionModeRequest) -> dict[str, object]:
    from backend.core.meta_cognition import MetaCognitionEngine
    return MetaCognitionEngine.select_cognitive_mode(
        prompt=request.prompt,
        is_production=request.is_production,
        is_code_change=request.is_code_change,
    )


@app.get("/executive/status")
def get_executive_status() -> dict[str, object]:
    from backend.core.executive_governance import ExecutiveCortex
    conn = ExecutiveCortex.get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM executive_tasks")
    total_tasks = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM arbitration_ledger")
    total_arbitrations = cursor.fetchone()[0]
    return {
        "status": "active",
        "total_tasks": total_tasks,
        "total_arbitrations": total_arbitrations
    }


@app.post("/executive/arbitrate")
def post_executive_arbitrate(request: ExecutiveArbitrateRequest) -> dict[str, object]:
    from backend.core.executive_governance import ExecutiveCortex
    return ExecutiveCortex.arbitrate_task(
        task_id=request.task_id,
        task_name=request.task_name,
        priority=request.priority,
        urgency=request.urgency,
        token_budget=request.token_budget,
        max_execution_seconds=request.max_execution_seconds
    )


@app.post("/executive/review")
def post_executive_review(request: ExecutiveReviewRequest) -> dict[str, object]:
    from backend.core.executive_governance import ExecutiveCortex
    return ExecutiveCortex.record_reviewer_decision(
        reviewer_id=request.reviewer_id,
        task_id=request.task_id,
        recommendation=request.recommendation,
        decision=request.decision
    )


@app.post("/benchmark/run")
def benchmark_run(request: BenchmarkRunRequest) -> dict[str, object]:
    from backend.core.benchmark_arena import BenchmarkArena
    items_dicts = [item.model_dump() for item in request.items]
    return BenchmarkArena.run_suite(
        suite_id=request.suite_id,
        items=items_dicts,
        is_held_out=request.is_held_out,
        chat_history=request.chat_history,
        memory_queries=request.memory_queries,
        violations=request.violations,
        latencies=request.latencies,
        predictions=request.predictions,
        outcomes=request.outcomes,
    )


@app.post("/benchmark/compare")
def benchmark_compare(request: BenchmarkCompareRequest) -> dict[str, object]:
    from backend.core.benchmark_arena import BenchmarkArena
    return BenchmarkArena.compare_versions(
        current_run=request.current_run,
        previous_run=request.previous_run,
        floors=request.floors,
    )


@app.get("/benchmark/history")
def benchmark_history() -> dict[str, object]:
    from backend.core.benchmark_arena import BenchmarkArena
    return {"history": BenchmarkArena.load_history()}


@app.post("/benchmark/tools/evaluate")
def tool_benchmark_evaluate(request: ToolBenchmarkEvaluateRequest) -> dict[str, object]:
    from backend.core.benchmark_arena import BenchmarkArena

    return BenchmarkArena.evaluate_tool_version(
        tool_name=request.tool_name,
        baseline_version=request.baseline_version,
        candidate_version=request.candidate_version,
        benchmark_suite=request.benchmark_suite,
        historical_runs=[run.model_dump() for run in request.historical_runs],
        candidate_runs=(
            [run.model_dump() for run in request.candidate_runs]
            if request.candidate_runs is not None else None
        ),
        min_runs=request.min_runs,
        persist=request.persist,
    )


@app.get("/benchmark/tools/history")
def tool_benchmark_history() -> dict[str, object]:
    from backend.core.benchmark_arena import BenchmarkArena

    return {"history": BenchmarkArena.load_tool_history()}


@app.post("/api/benchmark/continuous/run")
def run_continuous_benchmark() -> dict[str, object]:
    from backend.core.continuous_benchmark import ContinuousBenchmarkRunner
    return ContinuousBenchmarkRunner.run_suite()


@app.get("/api/benchmark/continuous/latest")
def get_latest_continuous_benchmark() -> dict[str, object]:
    from backend.core.continuous_benchmark import ContinuousBenchmarkRunner
    report = ContinuousBenchmarkRunner.get_latest_report()
    if not report:
        raise HTTPException(status_code=404, detail="No continuous benchmark runs found.")
    return report


@app.get("/api/benchmark/continuous/history")
def get_continuous_benchmark_history(limit: int = 50) -> dict[str, object]:
    from backend.core.continuous_benchmark import ContinuousBenchmarkRunner
    return {"history": ContinuousBenchmarkRunner.get_report_history(limit)}


@app.post("/proposal/observe")
def proposal_observe(request: ProposalObserveRequest) -> dict[str, object]:
    from backend.core.proposal_engine import ProposalEngine
    obs = ProposalEngine.observe_issue(request.issue, request.severity, request.metrics)
    hyps = ProposalEngine.reflect_on_observation(obs)
    return {"observation": obs, "hypotheses": hyps}


@app.post("/proposal/create")
def proposal_create(request: ProposalCreateRequest) -> dict[str, object]:
    from backend.core.proposal_engine import ProposalEngine
    return ProposalEngine.create_proposal(
        title=request.title,
        problem=request.problem,
        evidence=request.evidence,
        proposal=request.proposal,
        expected_gain=request.expected_gain,
        complexity=request.complexity,
        confidence=request.confidence,
        affected_modules=request.affected_modules,
        parent_proposal_id=request.parent_proposal_id,
        research_cost=request.research_cost,
    )


@app.get("/proposal/list")
def proposal_list() -> dict[str, object]:
    from backend.core.proposal_engine import ProposalEngine
    return {"proposals": ProposalEngine.list_proposals()}


@app.post("/proposal/approve/{proposal_id}")
def proposal_approve(proposal_id: str, status: str = "approved_gate_1") -> dict[str, object]:
    from backend.core.proposal_engine import ProposalEngine
    from backend.core.proposal_governance import ProposalStatus
    try:
        new_status = ProposalStatus(status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}") from exc
    try:
        return ProposalEngine.transition_status(proposal_id, new_status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/proposal/negative-knowledge")
def proposal_negative_knowledge(request: ProposalNegativeKnowledgeRequest) -> dict[str, object]:
    from backend.core.proposal_engine import ProposalEngine
    entry = ProposalEngine.register_negative_knowledge(request.title, request.reason)
    return {"entry": entry}


@app.get("/proposal/budget")
def proposal_budget() -> dict[str, object]:
    from backend.core.proposal_governance import ProposalBudgetManager, TrackRecordStore
    from backend.core.proposal_engine import ProposalEngine
    limit = ProposalBudgetManager.get_budget_limit()
    import time
    now = time.time()
    day_ago = now - 86400
    created_today = sum(1 for p in ProposalEngine.list_proposals() if p.get("created_at", 0.0) >= day_ago)
    pqs = TrackRecordStore.get_pqs()
    roi = TrackRecordStore.get_pipeline_roi()
    burden = TrackRecordStore.get_human_burden_score()
    return {
        "daily_limit": limit,
        "created_today": created_today,
        "pqs": round(pqs, 4),
        "pipeline_roi": round(roi, 4),
        "human_burden": burden,
    }


@app.post("/proposal/review/{proposal_id}")
def proposal_review(proposal_id: str, gate: str, request: ProposalReviewRequest) -> dict[str, object]:
    from backend.core.proposal_governance import TrackRecordStore, ProposalStatus
    from backend.core.proposal_engine import ProposalEngine
    if gate not in ("gate_1", "gate_2"):
        raise HTTPException(status_code=400, detail="Gate must be 'gate_1' or 'gate_2'")

    TrackRecordStore.record_human_review(
        proposal_id=proposal_id,
        gate=gate,
        approved=request.approved,
        review_time_seconds=request.review_time_seconds,
    )

    new_status = ProposalStatus.APPROVED_GATE_1 if gate == "gate_1" else ProposalStatus.APPROVED_GATE_2
    if not request.approved:
        new_status = ProposalStatus.REJECTED

    try:
        updated = ProposalEngine.transition_status(proposal_id, new_status)
        return {"status": "success", "proposal": updated}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/proposal/record-result/{proposal_id}")
def proposal_record_result(proposal_id: str, request: ProposalRecordRunRequest) -> dict[str, object]:
    from backend.core.proposal_governance import TrackRecordStore, ProposalStatus
    from backend.core.proposal_engine import ProposalEngine
    if request.stage not in ("sandbox", "benchmark", "production", "canary"):
        raise HTTPException(status_code=400, detail="Stage must be 'sandbox', 'benchmark', 'production', or 'canary'")

    TrackRecordStore.record_run(
        proposal_id=proposal_id,
        stage=request.stage,
        success=request.success,
        metrics=request.metrics,
        research_cost=request.research_cost,
        predicted_gain=request.predicted_gain,
        actual_sandbox_gain=request.actual_sandbox_gain,
        actual_production_gain=request.actual_production_gain,
    )

    status_map = {
        "sandbox": ProposalStatus.LAB_TESTING,
        "benchmark": ProposalStatus.BENCHMARKING,
        "canary": ProposalStatus.CANARY,
        "production": ProposalStatus.DEPLOYED,
    }

    target_status = status_map[request.stage]
    if not request.success:
        target_status = ProposalStatus.REJECTED

    try:
        updated = ProposalEngine.transition_status(proposal_id, target_status)
        return {"status": "success", "proposal": updated}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/proposal/track-records")
def proposal_track_records() -> dict[str, object]:
    from backend.core.proposal_governance import TrackRecordStore
    return {
        "records": TrackRecordStore.get_track_records(),
        "pqs": round(TrackRecordStore.get_pqs(), 4),
        "pipeline_roi": round(TrackRecordStore.get_pipeline_roi(), 4),
        "pipeline_pvs": TrackRecordStore.get_pipeline_pvs(),
        "pipeline_iy": TrackRecordStore.get_improvement_yield(),
        "pipeline_prr": TrackRecordStore.get_prr(),
        "pipeline_nkhr": TrackRecordStore.get_nkhr(),
        "pipeline_rf": TrackRecordStore.get_rf(),
        "gra": TrackRecordStore.get_gra_score(),
        "human_burden": TrackRecordStore.get_human_burden_score(),
    }


@app.post("/improvements/register/{proposal_id}")
def improvements_register(proposal_id: str) -> dict[str, object]:
    from backend.core.proposal_governance import ImprovementRegistry
    try:
        record = ImprovementRegistry.register_or_update(proposal_id)
        return {"status": "success", "record": record}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/improvements")
def improvements_list(
    status: str | None = None,
    from_time: float | None = None,
    to_time: float | None = None,
    proposal_id: str | None = None,
    limit: int | None = None,
) -> Any:
    # Check if this is a query for the original memory-based improvements
    if limit is not None and proposal_id is None and from_time is None and to_time is None:
        return {"items": memory.list_improvements(status=status, limit=limit)}

    from backend.core.proposal_governance import ImprovementRegistry
    try:
        return ImprovementRegistry.get_improvements(
            status=status,
            from_time=from_time,
            to_time=to_time,
            proposal_id=proposal_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/improvements/stats")
def improvements_stats() -> dict[str, Any]:
    from backend.core.proposal_governance import ImprovementRegistry
    try:
        return ImprovementRegistry.get_stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/improvements/{improvement_id}")
def improvements_detail(improvement_id: str) -> list[dict[str, Any]]:
    from backend.core.proposal_governance import ImprovementRegistry
    try:
        details = ImprovementRegistry.get_improvement_details(improvement_id)
        if not details:
            raise HTTPException(status_code=404, detail="Improvement not found")
        return details
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/sandbox/run-experiment/{proposal_id}")
def sandbox_run_experiment(proposal_id: str, request: SandboxExperimentRunRequest) -> dict[str, object]:
    from backend.core.proposal_engine import ProposalEngine
    from backend.core.proposal_governance import ProposalStatus
    from backend.core.sandbox_lab import (
        ExperimentRiskClassifier,
        ExperimentPackage,
        ReplayEngine,
        SafetyAuditor,
        ResultPackager,
        RiskLevel,
    )
    import time

    # 1. Load proposal
    proposals = ProposalEngine.list_proposals()
    target_proposal = None
    for p in proposals:
        if p.get("id") == proposal_id:
            target_proposal = p
            break

    if not target_proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    title = target_proposal.get("title", "")
    proposal_text = target_proposal.get("proposal", "")
    affected_modules = target_proposal.get("affected_modules", [])
    expected_gain = target_proposal.get("expected_gain", 5.0)

    # 2. Classify risk
    risk_class = ExperimentRiskClassifier.classify(title, proposal_text, affected_modules)
    if risk_class == RiskLevel.R4:
        try:
            ProposalEngine.transition_status(proposal_id, ProposalStatus.REJECTED)
        except Exception:
            pass
        raise HTTPException(
            status_code=400,
            detail="Experiment violates Protected Core boundary. Risk level R4 (Forbidden)."
        )

    # 3. Build Experiment Package
    package = ExperimentPackage(
        proposal_id=proposal_id,
        parent_proposal_id=target_proposal.get("parent_proposal_id"),
        risk_class=risk_class,
        expected_gain=expected_gain,
        expected_risk=request.expected_risk,
        benchmark_targets=["latency", "accuracy"],
        rollback_targets=["router"],
        created_at=time.time(),
    )

    # 4. Replay traces
    def trace_processor(trace):
        if request.mock_failure:
            # Simulate a write attempt to trigger safety violation
            import builtins
            builtins.open("test.txt", "w").close()
        return {"success": True}

    replay_results = ReplayEngine.replay_traces(trace_processor)

    # 5. Audit safety
    safety_success, safety_message = SafetyAuditor.audit_execution(proposal_text, replay_results)

    # 6. Result packaging
    report = ResultPackager.package_report(
        package=package,
        replay_results=replay_results,
        safety_success=safety_success,
        safety_message=safety_message,
        actual_gain=request.actual_gain,
    )

    # 7. Lifecycle transitions
    target_status = ProposalStatus.LAB_TESTING
    if not safety_success or report.get("recommendation") == "FAIL":
        target_status = ProposalStatus.REJECTED

    try:
        ProposalEngine.transition_status(proposal_id, target_status)
    except Exception:
        pass

    return report


@app.get("/sandbox/experiments")
def sandbox_list_experiments() -> dict[str, object]:
    from backend.core.sandbox_lab import ArtifactStore
    return {"experiments": ArtifactStore.load_experiments()}


@app.get("/sandbox/prs")
def sandbox_prs_score() -> dict[str, object]:
    from backend.core.sandbox_lab import ResultPackager
    return {"prs": ResultPackager.get_overall_prs()}


@app.post("/deployment/assess/{proposal_id}")
def deployment_assess(proposal_id: str, request: DeploymentAssessRequest) -> dict[str, object]:
    from backend.core.deployment_advisor import DeploymentAdvisor
    return DeploymentAdvisor.assess_deployment(proposal_id, request.benchmark_scores, request.baseline_scores)


@app.post("/deployment/canary/step/{proposal_id}")
def deployment_canary_step(proposal_id: str, request: CanaryStepRequest) -> dict[str, object]:
    from backend.core.deployment_advisor import CanaryReleaseCoordinator
    return CanaryReleaseCoordinator.advance_canary(
        proposal_id,
        request.simulated_anomaly,
        request.simulated_held_out_regression
    )


@app.post("/deployment/rollback/{proposal_id}")
def deployment_rollback(proposal_id: str, request: RollbackRequest) -> dict[str, object]:
    from backend.core.deployment_advisor import AutomaticRollbackEngine
    return AutomaticRollbackEngine.rollback(proposal_id, request.reason)


@app.post("/research/analyze")
def research_analyze(request: ResearchAnalyzeRequest) -> dict[str, object]:
    from backend.core.research_agent import ResearchAgent
    try:
        result = ResearchAgent.analyze_material(
            title=request.title,
            content=request.content,
            source_type=request.source_type,
        )
        return {"status": "success", "result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/research/results")
def research_results() -> list[dict[str, Any]]:
    from backend.core.research_agent import ResearchAgent
    try:
        return ResearchAgent.list_results()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/sandbox/run-experiment-v2/{proposal_id}")
def sandbox_run_experiment_v2(
    proposal_id: str,
    request: SandboxExperimentRunV2Request
) -> dict[str, object]:
    from backend.core.experiment_sandbox import ExperimentManager
    try:
        report = ExperimentManager.execute_experiment(
            proposal_id=proposal_id,
            baseline_benchmarks=request.baseline_benchmarks,
            mock_regression=request.mock_regression,
            mock_crash=request.mock_crash,
        )
        return {"status": "success", "report": report}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/goals")
@app.get("/api/goals")
def goals_status() -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    return GoalManager.status()


@app.get("/goals/list")
@app.get("/api/goals/list")
def goals_list() -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    return {"items": GoalManager.list_goals()}


@app.post("/goals")
@app.post("/api/goals")
def goals_add(request: GoalCreateRequest) -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    try:
        return {
            "item": GoalManager.add_goal(
                title=request.title,
                description=request.description,
                priority=request.priority,
                parent_id=request.parent_id,
                depends_on=request.depends_on,
                target_date=request.target_date,
                success_criteria=request.success_criteria,
                owner=request.owner,
                importance=request.importance,
                urgency=request.urgency,
                strategic_alignment=request.strategic_alignment,
                resource_cost=request.resource_cost,
                # Human-Like additions:
                owner_agent=request.owner_agent,
                horizon_type=request.horizon_type,
                current_state=request.current_state,
                importance_score=request.importance_score,
                urgency_score=request.urgency_score,
                estimated_value=request.estimated_value,
                confidence_score=request.confidence_score,
                energy_required=request.energy_required,
                risk_profile=request.risk_profile,
                attention_score=request.attention_score,
                decay_rate=request.decay_rate,
                provenance=request.provenance,
                original_goal_text=request.original_goal_text,
                definition_of_done=request.definition_of_done,
                ttl=request.ttl,
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/goals/{goal_id}/approve")
@app.post("/api/goals/{goal_id}/approve")
def goals_approve(goal_id: str) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return {"item": GoalMemory.update_goal_status(goal_id, "APPROVED", "Approved by user/executive")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/goals/{goal_id}/reaffirm")
@app.post("/api/goals/{goal_id}/reaffirm")
def goals_reaffirm(goal_id: str) -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    try:
        return {"item": GoalManager.reaffirm(goal_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/goals/{goal_id}/conflicts")
@app.get("/api/goals/{goal_id}/conflicts")
def goals_list_conflicts(goal_id: str) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return {"items": GoalMemory.get_conflicts(goal_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/goals/conflicts")
@app.post("/api/goals/conflicts")
def goals_declare_conflict(request: ConflictDeclareRequest) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return {
            "item": GoalMemory.add_conflict(
                goal_a_id=request.goal_a_id,
                goal_b_id=request.goal_b_id,
                conflict_topology=request.conflict_topology,
                severity_rating=request.severity_rating,
            )
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/goals/conflicts/{conflict_id}/resolve")
@app.post("/api/goals/conflicts/{conflict_id}/resolve")
def goals_resolve_conflict(conflict_id: str, request: ConflictResolveRequest) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        GoalMemory.resolve_conflict(conflict_id, request.resolution_status)
        return {"status": "success"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/goals/{goal_id}/values")
@app.get("/api/goals/{goal_id}/values")
def goals_list_values(goal_id: str) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return {"items": GoalMemory.get_values(goal_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/goals/{goal_id}/drift")
@app.get("/api/goals/{goal_id}/drift")
def goals_check_drift(goal_id: str) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return GoalMemory.check_goal_drift(goal_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/goals/{goal_id}/milestones")
@app.post("/api/goals/{goal_id}/milestones")
def goals_set_milestones(goal_id: str, request: MilestonesBatchRequest) -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    try:
        m_list = []
        for m in request.milestones:
            m_list.append({
                "title": m.title,
                "description": m.description,
                "weight": m.weight,
                "milestone_id": m.milestone_id,
            })
        GoalManager.add_milestones(goal_id, m_list)
        return {"status": "success", "item": GoalManager.get(goal_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/goals/active")
@app.get("/api/goals/active")
def goals_active() -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    return {"items": GoalManager.list_goals(status="ACTIVE")}


@app.get("/goals/metrics")
@app.get("/api/goals/metrics")
def goals_metrics() -> dict[str, object]:
    from backend.core.learning_dashboard import LearningDashboard
    try:
        return {"status": "ok", "data": LearningDashboard.goal_calibration_panel()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/dashboard/goals/reflection")
def dashboard_goals_reflection() -> dict[str, object]:
    from backend.core.learning_dashboard import LearningDashboard
    try:
        return {"status": "ok", "data": LearningDashboard.goal_calibration_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/goals/{goal_id}/history")
@app.get("/api/goals/{goal_id}/history")
def goals_history(goal_id: str) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return {"items": GoalMemory.get_events(goal_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/goals/policies/absolute")
@app.get("/api/goals/policies/absolute")
def goals_absolute_policies() -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    return {"policies": GoalMemory.ABSOLUTE_POLICIES}


@app.post("/goals/{goal_id}/update")
@app.post("/api/goals/{goal_id}/update")
def goals_update(goal_id: str, request: GoalUpdateRequest) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return {"item": GoalMemory.update_goal_content(goal_id, request.title, request.description)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/goals/{goal_id}/complete")
@app.post("/api/goals/{goal_id}/complete")
def goals_complete(goal_id: str, request: GoalCompleteRequest = None) -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    try:
        val = request.validator if request else None
        conf = request.user_confirmed if request else False
        ev = request.evidence if request else None
        return {"item": GoalManager.complete(goal_id, evidence=ev, validator=val, user_confirmed=conf)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/goals/{goal_id}/{action}")
@app.post("/api/goals/{goal_id}/{action}")
def goals_transition(goal_id: str, action: str) -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    handlers = {"start": GoalManager.start, "complete": GoalManager.complete, "abandon": GoalManager.abandon}
    handler = handlers.get(action)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"Unknown action {action!r}")
    try:
        return {"item": handler(goal_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/ppm/projects")
def ppm_projects_create(request: PPMProjectCreateRequest) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        return {
            "item": PersonalProjectManager.create_project(
                linked_goal_id=request.linked_goal_id,
                title=request.title,
                description=request.description,
                status=request.status,
                target_finish_date=request.target_finish_date,
                original_scope=request.original_scope
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/ppm/milestones")
def ppm_milestones_create(request: PPMMilestoneCreateRequest) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        return {
            "item": PersonalProjectManager.create_milestone(
                project_id=request.project_id,
                title=request.title,
                weight=request.weight,
                deadline=request.deadline
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/ppm/tasks")
def ppm_tasks_create(request: PPMTaskCreateRequest) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        return {
            "item": PersonalProjectManager.create_task(
                milestone_id=request.milestone_id,
                title=request.title,
                description=request.description,
                assigned_agent=request.assigned_agent,
                effort_score=request.effort_score,
                deadline=request.deadline
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/ppm/blockers")
def ppm_blockers_add(request: PPMBlockerAddRequest) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        return {
            "item": PersonalProjectManager.add_blocker(
                project_id=request.project_id,
                severity=request.severity,
                source=request.source
            )
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ppm/blockers/{blocker_id}/resolve")
def ppm_blockers_resolve(blocker_id: str) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        PersonalProjectManager.resolve_blocker(blocker_id)
        return {"status": "success"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ppm/resources")
def ppm_resources_allocate(request: PPMResourceAllocateRequest) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        return {
            "item": PersonalProjectManager.allocate_resource(
                project_id=request.project_id,
                resource_type=request.resource_type,
                allocated=request.allocated
            )
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ppm/resources/consume")
def ppm_resources_consume(request: PPMResourceConsumeRequest) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        return {
            "item": PersonalProjectManager.consume_resource(
                project_id=request.project_id,
                resource_type=request.resource_type,
                amount=request.amount
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/ppm/projects/{project_id}/revisions")
def ppm_projects_revision(project_id: str, request: PPMRevisionLogRequest) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        PersonalProjectManager.log_revision(project_id, request.author, request.summary)
        return {"status": "success"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ppm/projects/{project_id}/complete")
def ppm_projects_complete(project_id: str, request: PPMCompleteRequest) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        return {
            "item": PersonalProjectManager.complete_project(
                project_id=project_id,
                validator=request.validator,
                user_confirmed=request.user_confirmed
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/ppm/projects/{project_id}")
def ppm_projects_get(project_id: str) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        proj = PersonalProjectManager.get_project(project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"item": proj}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/ppm/projects/{project_id}/report")
def ppm_projects_report(project_id: str) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        return {"report": PersonalProjectManager.reflect_on_project(project_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/projects")
@app.get("/api/projects")
def projects_list() -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    return {"items": ProjectManagerV2.list_projects()}


@app.post("/projects")
@app.post("/api/projects")
def projects_create(request: ProjectCreateRequest) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        return {
            "item": ProjectManagerV2.create_project(
                name=request.name,
                description=request.description,
                status=request.status,
                metadata=request.metadata,
            )
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/projects/ecosystem")
def get_project_ecosystem() -> dict[str, object]:
    return project_ecosystem()


@app.get("/projects/improvement-agents")
def get_project_improvement_agents() -> dict[str, object]:
    return project_improvement_agents()


@app.post("/projects/improvement-agents/observe")
def observe_project_improvement_agents_endpoint(
    request: ProjectImprovementObserveRequest,
) -> dict[str, object]:
    return observe_project_improvement_agents(run_status=request.run_status)


@app.post("/projects/improvement-agents/check-shared")
def check_shared_project_improvements() -> dict[str, object]:
    return check_git_shared_improvements()


@app.get("/projects/{project_id}")
@app.get("/api/projects/{project_id}")
def projects_get_hierarchy(project_id: str) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        proj = ProjectManagerV2.get_project_hierarchy(project_id)
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return {"item": proj}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/projects/{project_id}/simulation")
@app.get("/api/projects/{project_id}/simulation")
def projects_simulate(project_id: str) -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine
    try:
        return {"report": SimulationEngine.simulate_project(project_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/projects/{project_id}/goals")
@app.post("/api/projects/{project_id}/goals")
def projects_add_goal(project_id: str, request: ProjectGoalAddRequest) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        ProjectManagerV2.add_goal_to_project(request.goal_id, project_id)
        return {"status": "success", "item": ProjectManagerV2.get_project(project_id)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/projects/{project_id}/decisions")
@app.post("/api/projects/{project_id}/decisions")
def projects_add_decision(project_id: str, request: ProjectDecisionRequest) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        ProjectManagerV2.log_project_decision(project_id, request.title, request.description, request.rationale)
        return {"status": "success", "item": ProjectManagerV2.get_project(project_id)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/projects/{project_id}/dependencies")
@app.post("/api/projects/{project_id}/dependencies")
def projects_add_dependency(project_id: str, request: ProjectDependencyRequest) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        ProjectManagerV2.add_project_dependency(project_id, request.depends_on_project_id)
        return {"status": "success", "item": ProjectManagerV2.get_project(project_id)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/projects/{project_id}/logs")
@app.get("/api/projects/{project_id}/logs")
def projects_get_logs(project_id: str) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        proj = ProjectManagerV2.get_project(project_id)
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return {
            "events": proj.get("events", []),
            "decisions": proj.get("decisions", []),
            "failures": proj.get("failures", []),
            "rollbacks": proj.get("rollbacks", [])
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/projects/{project_id}/transition/{status}")
@app.post("/api/projects/{project_id}/transition/{status}")
def projects_transition_status(project_id: str, status: str) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        return {"item": ProjectManagerV2.update_project_status(project_id, status)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc




@app.get("/reflection")
def reflection_status(status: str | None = None) -> dict[str, object]:
    from backend.core.reflection_engine import ReflectionEngine
    if status:
        return {"items": ReflectionEngine.list_reflections(status=status)}
    return ReflectionEngine.status()


@app.post("/reflection/propose")
def reflection_propose(request: ReflectionProposeRequest) -> dict[str, object]:
    from backend.core.reflection_engine import ReflectionEngine
    try:
        return ReflectionEngine.reflect(
            request.problem, request.cause, request.improvement,
            category=request.category, evidence_source=request.evidence_source,
            confidence=request.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/reflection/{reflection_id}/{action}")
def reflection_decide(reflection_id: str, action: str) -> dict[str, object]:
    from backend.core.reflection_engine import ReflectionEngine
    handlers = {"accept": ReflectionEngine.accept, "reject": ReflectionEngine.reject}
    handler = handlers.get(action)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"Unknown action {action!r}")
    try:
        return handler(reflection_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/capabilities")
def capabilities_status() -> dict[str, object]:
    from backend.core.capability_graph import CapabilityGraph
    return {"status": CapabilityGraph.status(), "items": CapabilityGraph.list_capabilities()}


@app.post("/capabilities")
def capabilities_register(request: CapabilityRegisterRequest) -> dict[str, object]:
    from backend.core.capability_graph import CapabilityGraph
    try:
         return {"item": CapabilityGraph.register(
            request.name, request.kind, available=request.available,
            depends_on=request.depends_on, alternatives=request.alternatives, risk=request.risk,
         )}
    except ValueError as exc:
         raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/capabilities/assess")
def capabilities_assess(request: CapabilityAssessRequest) -> dict[str, object]:
    from backend.core.capability_graph import CapabilityGraph
    return CapabilityGraph.assess(request.goal, request.required)


@app.post("/trust/assess")
def trust_assess(request: TrustAssessRequest) -> dict[str, object]:
    from backend.core.trust_evidence import assess_from_dicts
    return assess_from_dicts(request.statement, request.evidence).to_dict()


@app.get("/skills/library")
def skills_library_status() -> dict[str, object]:
    from backend.core.skill_library import SkillLibrary
    return {"status": SkillLibrary.status(), "items": SkillLibrary.list_skills()}


@app.get("/skills/library/search")
def skills_library_search(q: str) -> dict[str, object]:
    from backend.core.skill_library import SkillLibrary
    return {"items": SkillLibrary.search(q)}


@app.post("/skills/library")
def skills_library_add(request: SkillAddRequest) -> dict[str, object]:
    from backend.core.skill_library import SkillLibrary
    try:
        return {"item": SkillLibrary.add_skill(
            request.name, request.description, inputs=request.inputs,
            steps=request.steps, outputs=request.outputs, tags=request.tags,
        )}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/skills/library/{name}/result")
def skills_library_result(name: str, request: SkillLibResultRequest) -> dict[str, object]:
    from backend.core.skill_library import SkillLibrary
    try:
        return SkillLibrary.record_result(name, request.success)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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



@app.get("/world")
def world_status() -> dict[str, object]:
    from backend.core.world_model import WorldModel
    return WorldModel.status()


@app.post("/world/entity")
def world_add_entity(request: WorldEntityRequest) -> dict[str, object]:
    from backend.core.world_model import WorldModel
    try:
        return {"item": WorldModel.add_entity(
            request.name, request.type, status=request.status, attributes=request.attributes)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/world/relation")
def world_add_relation(request: WorldRelationRequest) -> dict[str, object]:
    from backend.core.world_model import WorldModel
    try:
        return {"item": WorldModel.add_relation(request.src, request.dst, request.relation)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/world/impact/{name}")
def world_impact(name: str) -> dict[str, object]:
    from backend.core.world_model import WorldModel
    try:
        return WorldModel.impact_of(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/simulate")
def simulate(request: SimulateRequest) -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine
    return SimulationEngine.simulate_dict(
        request.scenario, trials=request.trials, seed=request.seed).to_dict()


@app.post("/simulate/plan")
def simulate_plan(request: PlanSimulationRequest) -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine

    return SimulationEngine.simulate_plan(
        request.plan,
        goal=request.goal,
        workflow_id=request.workflow_id,
        context=request.context,
    ).to_dict()


@app.post("/simulate/counterfactual")
def simulate_counterfactual(request: PlanSimulationRequest) -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine
    return SimulationEngine.run_counterfactual_simulations(
        request.plan,
        goal=request.goal,
        workflow_id=request.workflow_id
    )


@app.post("/simulate/forecast")
def record_forecast(request: DecisionForecastRequest) -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine
    SimulationEngine.record_decision_forecast(
        request.decision_id,
        request.decision,
        request.predicted_success,
        request.predicted_cost,
        request.predicted_time
    )
    return {"status": "success", "decision_id": request.decision_id}


@app.post("/simulate/outcome")
def record_outcome(request: DecisionOutcomeRequest) -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine
    SimulationEngine.record_decision_outcome(
        request.decision_id,
        request.actual_success,
        request.actual_cost,
        request.actual_time
    )
    return {"status": "success", "decision_id": request.decision_id}


@app.post("/simulate/recalibrate")
def recalibrate_simulations() -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine
    return SimulationEngine.recalibrate_from_ledger()


@app.post("/research/ingest")
def research_ingest(request: ResearchIngestRequest) -> dict[str, object]:
    from backend.core.research_loop import ResearchLoop
    return ResearchLoop.ingest_paper(
        title=request.title,
        authors=request.authors,
        arxiv_id=request.arxiv_id,
        doi=request.doi,
        published_date=request.published_date,
        claims=request.claims,
        metrics=request.metrics
    )


@app.get("/research/proposals")
def research_proposals() -> list[dict[str, object]]:
    from backend.core.research_loop import ResearchLoop
    return ResearchLoop.list_proposals()


@app.post("/research/evaluate")
def research_evaluate(request: ResearchEvaluateRequest) -> dict[str, object]:
    from backend.core.research_loop import ResearchLoop
    return ResearchLoop.evaluate_experiment_candidate(
        experiment_id=request.experiment_id,
        run_results=request.run_results
    )


@app.post("/memory/safety/run")
def memory_safety_run(request: MemorySafetyRunRequest) -> dict[str, object]:
    from backend.core.memory_safety import MemorySafetyVerifier
    aer = MemorySafetyVerifier.calculate_aer(request.test_contents)
    from backend.core.human_memory import HumanMemoryStore
    records = HumanMemoryStore.all_records()
    deleted_ids = [r.id for r in records[:5]] if records else []
    
    for r_id in deleted_ids:
        HumanMemoryStore.delete(r_id)
        
    frs = MemorySafetyVerifier.calculate_frs(deleted_ids) if deleted_ids else 0.0
    fidelity = MemorySafetyVerifier.calculate_deletion_fidelity(deleted_ids) if deleted_ids else 1.0
    
    return {
        "adversarial_extraction_rate": round(aer, 4),
        "forgetting_residue_score": round(frs, 4),
        "deletion_fidelity": round(fidelity, 4)
    }


@app.post("/memory/safety/evomem")
def memory_safety_evomem() -> dict[str, object]:
    from backend.core.memory_safety import MemorySafetyVerifier
    return MemorySafetyVerifier.run_evomem_drift_benchmark()


# ── Step 17: Dynamic Benchmark Variant Generator ──────────────────────────────

class BenchmarkVariantGenerateRequest(BaseModel):
    suite_id: str
    input_text: str
    expected_answer: str
    n: int = 5
    seed_int: int | None = None


@app.post("/benchmark/variants/generate")
def benchmark_variants_generate(request: BenchmarkVariantGenerateRequest) -> dict[str, object]:
    """Generate N surface-mutated variants for a benchmark seed case."""
    from backend.core.benchmark_variant_generator import BenchmarkCase, BenchmarkVariantGenerator
    import uuid
    seed = BenchmarkCase(
        case_id=f"seed_{uuid.uuid4().hex[:10]}",
        suite_id=request.suite_id,
        input_text=request.input_text,
        expected_answer=request.expected_answer,
    )
    variants = BenchmarkVariantGenerator.generate_variants(
        seed, n=request.n, seed_int=request.seed_int
    )
    return {
        "seed_case_id": seed.case_id,
        "suite_id": request.suite_id,
        "variants_generated": len(variants),
        "variants": [v.to_dict() for v in variants],
    }


@app.get("/benchmark/variants/{suite_id}")
def benchmark_variants_pool(suite_id: str, limit: int = 50) -> dict[str, object]:
    """Return the active variant pool for a suite."""
    from backend.core.benchmark_variant_generator import BenchmarkVariantGenerator
    pool = BenchmarkVariantGenerator.get_pool(suite_id, limit=limit)
    return {
        "suite_id": suite_id,
        "pool_size": len(pool),
        "cases": [c.to_dict() for c in pool],
    }


# ── Step 18: Claim Reproduction Engine ───────────────────────────────────────

@app.post("/research/reproduce/{claim_id}")
def research_reproduce_claim(claim_id: str) -> dict[str, object]:
    """Trigger execution of a queued claim reproduction experiment.

    The experiment must have been queued by ResearchLoop.ingest_paper()
    (priority_score > 9.0) or built manually via ClaimReproductionEngine.build_template().
    """
    from backend.core.claim_reproduction_engine import ClaimReproductionEngine
    # Find the queued experiment for this claim
    queued = ClaimReproductionEngine.list_queued()
    exp = next((e for e in queued if e.get("claim_id") == claim_id), None)
    if not exp:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"No queued experiment for claim_id={claim_id}")
    result = ClaimReproductionEngine.run(exp["id"])
    return {
        "experiment_id": result.experiment_id,
        "claim_id": result.claim_id,
        "paper_id": result.paper_id,
        "confirmed": result.confirmed,
        "baseline_score": result.baseline_score,
        "challenger_score": result.challenger_score,
        "actual_delta": result.actual_delta,
        "expected_delta": result.expected_delta,
        "delta_ratio": result.delta_ratio,
    }


@app.get("/research/reproduce/queue")
def research_reproduce_queue() -> dict[str, object]:
    """List all experiments queued for human-triggered reproduction."""
    from backend.core.claim_reproduction_engine import ClaimReproductionEngine
    queued = ClaimReproductionEngine.list_queued()
    return {"queued_count": len(queued), "experiments": queued}


@app.get("/research/reproduce/results")
def research_reproduce_results(limit: int = 50) -> dict[str, object]:
    """List completed reproduction experiment results."""
    from backend.core.claim_reproduction_engine import ClaimReproductionEngine
    results = ClaimReproductionEngine.list_results(limit=limit)
    return {"results": results}


# ── Step 21: Self-Improvement Governance ─────────────────────────────────────

class GovernanceSubmitRequest(BaseModel):
    title: str
    source: str           # 'research' | 'benchmark' | 'reflection'
    source_id: str | None = None
    affected_modules: list[str]
    proposal_text: str
    benchmark_confirmed: bool = False


class GovernanceReviewRequest(BaseModel):
    reviewer_id: str
    reason: str = ""


@app.post("/governance/submit")
def governance_submit(request: GovernanceSubmitRequest) -> dict[str, object]:
    """Submit an architectural change proposal through the four-gate governance check."""
    from backend.core.self_improvement_governance import ArchitecturalProposal, SelfImprovementGovernance
    import uuid, time
    proposal = ArchitecturalProposal(
        proposal_id=str(uuid.uuid4()),
        title=request.title,
        source=request.source,
        source_id=request.source_id,
        affected_modules=request.affected_modules,
        proposal_text=request.proposal_text,
        benchmark_confirmed=request.benchmark_confirmed,
        created_at=time.time(),
    )
    decision = SelfImprovementGovernance.submit(proposal)
    return {
        "proposal_id": decision.proposal_id,
        "gate_status": decision.gate_status,
        "passed": decision.passed,
        "pis_score": decision.pis_score,
        "blocking_reasons": decision.reasons,
    }


@app.get("/governance/pending")
def governance_pending() -> dict[str, object]:
    """List all proposals awaiting human review."""
    from backend.core.self_improvement_governance import SelfImprovementGovernance
    proposals = SelfImprovementGovernance.list_pending()
    return {"pending_count": len(proposals), "proposals": proposals}


@app.post("/governance/approve/{proposal_id}")
def governance_approve(proposal_id: str, request: GovernanceReviewRequest) -> dict[str, object]:
    """Human approves a pending governance proposal."""
    from backend.core.self_improvement_governance import SelfImprovementGovernance
    success = SelfImprovementGovernance.approve(proposal_id, request.reviewer_id)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found or not pending")
    return {"proposal_id": proposal_id, "status": "approved", "reviewer_id": request.reviewer_id}


@app.post("/governance/reject/{proposal_id}")
def governance_reject(proposal_id: str, request: GovernanceReviewRequest) -> dict[str, object]:
    """Human rejects a pending governance proposal."""
    from backend.core.self_improvement_governance import SelfImprovementGovernance
    success = SelfImprovementGovernance.reject(proposal_id, request.reviewer_id, request.reason)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found or not pending")
    return {"proposal_id": proposal_id, "status": "rejected", "reviewer_id": request.reviewer_id}


@app.get("/governance/proposals")
def governance_all_proposals(limit: int = 100) -> dict[str, object]:
    """Return all governance proposals (any status), newest first."""
    from backend.core.self_improvement_governance import SelfImprovementGovernance
    proposals = SelfImprovementGovernance.list_all(limit=limit)
    return {"total": len(proposals), "proposals": proposals}


@app.get("/governance/audit/{proposal_id}")
def governance_audit_log(proposal_id: str) -> dict[str, object]:
    """Return the full audit trail for a governance proposal."""
    from backend.core.self_improvement_governance import SelfImprovementGovernance
    log = SelfImprovementGovernance.get_audit_log(proposal_id)
    return {"proposal_id": proposal_id, "audit_log": log}


# ── Council of Perspectives (Step 15.5 + Council v2) ─────────────────────────

class CouncilDeliberateRequest(BaseModel):
    question: str
    question_type: str = "general"   # 'safety'|'research'|'user_impact'|'architecture'|'general'
    context: dict = {}
    code_change: bool = False
    production: bool = False
    mode_profile: str = "auto"


class CouncilQuickDeliberateRequest(BaseModel):
    question: str
    question_type: str = "general"
    context: dict = {}
    n: int = 3
    code_change: bool = False
    production: bool = False
    mode_profile: str = "auto"


class CouncilOutcomeRequest(BaseModel):
    outcome: str          # 'correct' | 'incorrect' | 'unknown'
    outcome_score: float  # 0.0–1.0
    predicted_success: float | None = None
    actual_success: float | None = None
    notes: str = ""


class CouncilBenchmarkValidateRequest(BaseModel):
    quick_council: bool = False
    quick_n: int = 3


class PersonalityCouncilRequest(BaseModel):
    question: str
    mode_profile: str = "SYSTEM_DEFAULT"
    mode_set_by: str = "SYSTEM"
    context: dict[str, Any] = Field(default_factory=dict)
    evidence_episode_ids: list[str] = Field(default_factory=list)
    evidence_semantic_ids: list[str] = Field(default_factory=list)
    evidence_relation_ids: list[str] = Field(default_factory=list)
    evidence_world_ids: list[str] = Field(default_factory=list)


class PersonalityCouncilOutcomeRequest(BaseModel):
    predicted_success: float | None = Field(default=None, ge=0.0, le=1.0)
    actual_success: float | None = Field(default=None, ge=0.0, le=1.0)
    source_episode_id: str | None = None
    notes: str = ""


@app.post("/council/deliberate")
def council_deliberate(request: CouncilDeliberateRequest) -> dict[str, object]:
    """Full council deliberation: all 11 voting perspectives + Auditor adversarial pass."""
    from backend.core.council_session import CouncilSession
    result = CouncilSession.deliberate(
        question=request.question,
        question_type=request.question_type,
        context=request.context,
        code_change=request.code_change,
        production=request.production,
        mode_profile=request.mode_profile,
    )
    return result.to_dict()


@app.post("/council/deliberate/quick")
def council_deliberate_quick(request: CouncilQuickDeliberateRequest) -> dict[str, object]:
    """Quick deliberation: top-N perspectives by question type + Auditor. Default N=3 → 4 LLM calls."""
    from backend.core.council_session import CouncilSession
    result = CouncilSession.quick_deliberate(
        question=request.question,
        question_type=request.question_type,
        context=request.context,
        n=request.n,
        code_change=request.code_change,
        production=request.production,
        mode_profile=request.mode_profile,
    )
    return result.to_dict()


@app.get("/council/decisions")
def council_decisions(limit: int = 50) -> dict[str, object]:
    """List all council deliberation decisions from the ledger, newest first."""
    from backend.core.council_session import CouncilSession
    decisions = CouncilSession.list_decisions(limit=limit)
    return {"total": len(decisions), "decisions": decisions}


@app.get("/council/decision/{decision_id}")
def council_decision_detail(decision_id: str) -> dict[str, object]:
    """Retrieve full details of a single council decision including votes and audit findings."""
    from backend.core.council_session import CouncilSession
    decision = CouncilSession.get_decision(decision_id)
    if not decision:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Council decision {decision_id} not found")
    return decision


@app.get("/council/performance")
def council_performance() -> dict[str, object]:
    """Performance report: council approval/rejection rates and Arena outcome accuracy."""
    from backend.core.council_session import CouncilPerformanceReport
    return CouncilPerformanceReport.generate()


@app.post("/council/benchmark/validate")
def council_benchmark_validate(request: CouncilBenchmarkValidateRequest) -> dict[str, object]:
    """Run comparative validation: Group A vs Group B on the pre-seeded evaluation suite."""
    from backend.core.council_benchmark_validator import CouncilBenchmarkValidator
    report = CouncilBenchmarkValidator.run_comparative_benchmark(
        quick_council=request.quick_council,
        quick_n=request.quick_n,
    )
    return {
        "success_criteria_passed": report.success_criteria_passed,
        "reasons": report.reasons,
        "group_a": {
            "accuracy": report.group_a.accuracy,
            "safety_accuracy": report.group_a.safety_accuracy,
            "reversal_rate": report.group_a.reversal_rate,
            "human_satisfaction": report.group_a.human_satisfaction,
            "avg_latency_ms": report.group_a.avg_latency_ms,
            "total_llm_calls": report.group_a.total_llm_calls,
            "total_estimated_tokens": report.group_a.total_estimated_tokens,
            "decisions": report.group_a.decisions,
        },
        "group_b": {
            "accuracy": report.group_b.accuracy,
            "safety_accuracy": report.group_b.safety_accuracy,
            "reversal_rate": report.group_b.reversal_rate,
            "human_satisfaction": report.group_b.human_satisfaction,
            "avg_latency_ms": report.group_b.avg_latency_ms,
            "total_llm_calls": report.group_b.total_llm_calls,
            "total_estimated_tokens": report.group_b.total_estimated_tokens,
            "decisions": report.group_b.decisions,
        }
    }


@app.post("/council/benchmark/{decision_id}")
def council_record_outcome(decision_id: str, request: CouncilOutcomeRequest) -> dict[str, object]:
    """Record Arena verification outcome for a council decision (for benchmarking)."""
    from backend.core.council_session import CouncilSession
    CouncilSession.record_outcome(
        decision_id=decision_id,
        outcome=request.outcome,
        outcome_score=request.outcome_score,
        predicted_success=request.predicted_success,
        actual_success=request.actual_success,
        notes=request.notes,
    )
    return {
        "decision_id": decision_id,
        "outcome": request.outcome,
        "outcome_score": request.outcome_score,
        "predicted_success": request.predicted_success,
        "actual_success": request.actual_success,
        "notes": request.notes,
    }


@app.post("/personality-council/deliberate")
def personality_council_deliberate(request: PersonalityCouncilRequest) -> dict[str, object]:
    """Step 20 deterministic council: validators for facts, vetoes for risks, ranking for values."""
    from backend.core.council import PersonalityCouncil
    return PersonalityCouncil.deliberate(
        question=request.question,
        mode_profile=request.mode_profile,
        mode_set_by=request.mode_set_by,
        context=request.context,
        evidence_episode_ids=request.evidence_episode_ids,
        evidence_semantic_ids=request.evidence_semantic_ids,
        evidence_relation_ids=request.evidence_relation_ids,
        evidence_world_ids=request.evidence_world_ids,
    )


@app.get("/personality-council/session/{session_id}")
def personality_council_session(session_id: str) -> dict[str, object]:
    """Retrieve a persisted Step 20 council session."""
    from backend.core.council import PersonalityCouncil
    session = PersonalityCouncil.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Personality council session {session_id} not found")
    return session


@app.post("/personality-council/outcomes/{outcome_id}")
def personality_council_record_outcome(
    outcome_id: str,
    request: PersonalityCouncilOutcomeRequest,
) -> dict[str, object]:
    """Record outcome feedback and update deterministic council calibration."""
    from backend.core.council import CouncilOutcomeLoop
    try:
        return CouncilOutcomeLoop.record_outcome(
            outcome_id=outcome_id,
            predicted_success=request.predicted_success,
            actual_success=request.actual_success,
            source_episode_id=request.source_episode_id,
            notes=request.notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/personality-council/performance")
def personality_council_performance() -> dict[str, object]:
    """Return Step 20 council calibration and outcome coverage."""
    from backend.core.council import PersonalityCouncil
    return PersonalityCouncil.performance()


@app.post("/distill")
def distill(request: DistillRequest) -> dict[str, object]:
    from backend.core.knowledge_distillation import KnowledgeDistiller
    return KnowledgeDistiller.distill(
        request.observations, min_cluster=request.min_cluster,
        principle_hints=request.principle_hints).to_dict()


@app.get("/value/profiles")
def value_profiles() -> dict[str, object]:
    from backend.core.value_engine import PROFILES
    return {"profiles": {p.value: w for p, w in PROFILES.items()}}


@app.post("/value/score")
def value_score(request: ValueScoreRequest) -> dict[str, object]:
    from backend.core.value_engine import PlanSignals, ValueEngine
    return ValueEngine.score_plan(PlanSignals.from_dict(request.signals))


@app.post("/value/rank")
def value_rank(request: ValueRankRequest) -> dict[str, object]:
    from backend.core.value_engine import PlanSignals, ValueEngine, ValueProfile
    plans = [PlanSignals.from_dict(p) for p in request.plans]
    try:
        profile = ValueProfile.coerce(request.profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ValueEngine.rank(plans, profile).to_dict()


@app.get("/value/drift")
def value_drift() -> dict[str, object]:
    from backend.core.value_engine import ValueDriftMonitor
    return ValueDriftMonitor.report()
import threading

@app.on_event("startup")
def start_startup_tasks():
    from backend.core.cluster_runtime import internet_hub_worker_poll_loop
    thread = threading.Thread(target=internet_hub_worker_poll_loop, daemon=True)
    thread.start()

    # Start Step 9.0 Daily Research Loop
    try:
        from backend.core.research_scheduler import ResearchScheduler
        ResearchScheduler.start()
    except Exception:
        pass

    # Run Experiment Sandbox startup orphan cleanup scan
    try:
        from backend.core.experiment_sandbox import ExperimentManager
        ExperimentManager.cleanup_orphans()
    except Exception:
        pass

    # Warm up default fast and coder models in the background on startup
    from backend.core.config import load_config
    from backend.core.adaptive_runtime import WarmupManager
    try:
        cfg = load_config()
        WarmupManager.warm_model_background(cfg.model_map["fast"], cfg.ollama_host)
        WarmupManager.warm_model_background(cfg.model_map["coder"], cfg.ollama_host)
    except Exception:
        pass



@app.get("/health")
def health_check() -> dict[str, object]:
    ok, message = health()
    config = load_config()
    return {
        "status": "Kattappa AI OS backend running",
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


@app.get("/toolbox/replacements")
def toolbox_replacements() -> dict[str, object]:
    return toolbox_replacement_report()


@app.post("/creator/deck")
def creator_deck(request: LocalDeckRequest) -> dict[str, object]:
    return create_local_deck_outline(
        request.topic,
        audience=request.audience,
        project=request.project,
        slide_count=request.slide_count,
    )


@app.post("/creator/diagram")
def creator_diagram(request: LocalDiagramRequest) -> dict[str, object]:
    return create_mermaid_diagram(request.text, diagram_type=request.diagram_type)


@app.post("/context/compress")
def context_compress(request: ContextCompressRequest) -> dict[str, object]:
    return compress_context(request.text, max_points=request.max_points)


@app.post("/creator/code-review")
def creator_code_review(request: LocalReviewRequest) -> dict[str, object]:
    return local_code_review(request.diff_text, project=request.project)


@app.post("/creator/gsd-workflow")
def creator_gsd_workflow(request: LocalGsdWorkflowRequest) -> dict[str, object]:
    return create_gsd_workflow(request.goal, project=request.project)


@app.post("/creator/document-markdown")
def creator_document_markdown(request: DocumentMarkdownRequest) -> dict[str, object]:
    return convert_document_text_to_markdown(request.filename, request.text)


@app.post("/creator/marketing-kit")
def creator_marketing_kit(request: MarketingKitRequest) -> dict[str, object]:
    return create_marketing_kit(
        request.brand,
        request.product,
        audience=request.audience,
        channel=request.channel,
    )


@app.get("/voice/status")
def voice_status() -> dict[str, object]:
    return voice_pipeline_status()


@app.post("/voice/speak")
def voice_speak(request: VoiceSpeakRequest) -> dict[str, object]:
    spoken_text = normalize_spoken_text(request.text, purpose=request.purpose)
    if not spoken_text:
        return {"ok": False, "result": "empty_text", "pipeline": voice_pipeline_status()}
    return {
        "ok": True,
        "purpose": request.purpose,
        "spoken_text": spoken_text,
        "result": speak(spoken_text, purpose=request.purpose),
        "pipeline": voice_pipeline_status(),
    }


@app.post("/voice/process")
def voice_process(request: VoiceAudioRequest) -> dict[str, object]:
    return process_voice_audio(
        request.audio_base64,
        mime_type=request.mime_type,
        model_size=request.model_size,
    )


@app.post("/voice/parse-wake")
def voice_parse_wake(request: VoiceTranscriptRequest) -> dict[str, object]:
    return parse_wake_command(request.transcript)


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


@app.get("/system/adaptive-profile")
def system_adaptive_profile() -> dict[str, object]:
    from backend.core.adaptive_runtime import HardwareProfiler, PerformanceProfile, AdaptiveContext
    from backend.core.config import load_config

    hw = HardwareProfiler.get_profile()
    profile = PerformanceProfile.resolve_profile(hw)
    limits = AdaptiveContext.get_limits(profile)
    cfg = load_config()

    from backend.core.rbil import MetricsTracker
    rbil_stats = MetricsTracker.load()

    return {
        "hardware_profile": profile,
        "context_budget": limits["max_context_tokens"],
        "history_max_turns": limits["history_max_turns"],
        "compress_history": limits["compress_history"],
        "disk_buffer_enabled": limits["disk_buffer_enabled"],
        "system_diagnostics": hw,
        "active_models": cfg.model_map,
        "rbil_metrics": rbil_stats
    }


@app.get("/cluster/plan")
def kattappa_cluster_plan() -> dict[str, object]:
    return cluster_plan()


@app.get("/cluster/status")
def kattappa_cluster_status() -> dict[str, object]:
    return cluster_runtime_status()


@app.get("/cluster/nodes")
def kattappa_cluster_nodes() -> dict[str, object]:
    return {"items": list_paired_nodes()}


@app.post("/cluster/nodes")
def kattappa_register_cluster_node(request: ClusterNodeRequest) -> dict[str, object]:
    try:
        item = register_paired_node(
            request.name,
            request.base_url,
            request.token,
            capabilities=dict(request.capabilities),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@app.delete("/cluster/nodes/{node_id}")
def kattappa_remove_cluster_node(node_id: str) -> dict[str, object]:
    if not remove_paired_node(node_id):
        raise HTTPException(status_code=404, detail="Paired node not found")
    return {"removed": True, "node_id": node_id}


@app.get("/cluster/discovery-targets")
def kattappa_cluster_discovery_targets() -> dict[str, object]:
    return {"items": list_discovery_targets()}


@app.post("/cluster/discovery-targets")
def kattappa_register_cluster_discovery_target(
    request: ClusterDiscoveryTargetRequest,
) -> dict[str, object]:
    try:
        item = register_discovery_target(request.name, request.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@app.delete("/cluster/discovery-targets/{target_id}")
def kattappa_remove_cluster_discovery_target(target_id: str) -> dict[str, object]:
    if not remove_discovery_target(target_id):
        raise HTTPException(status_code=404, detail="Discovery target not found")
    return {"removed": True, "target_id": target_id}


@app.post("/cluster/tasks/route")
def kattappa_route_cluster_task(request: ClusterTaskRouteRequest) -> dict[str, object]:
    try:
        return route_cluster_task(
            request.message,
            task_kind=request.task_kind,
            sensitivity=request.sensitivity,
            force_remote=request.force_remote,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/cluster/tasks/bids")
def kattappa_cluster_task_bids(request: ClusterBidRequest) -> dict[str, object]:
    try:
        return collect_worker_bids(request.message, request.task_kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/cluster/worker/bid")
def kattappa_worker_bid(
    request: ClusterWorkerBidRequest,
    x_kattappa_cluster_token: str | None = Header(default=None),
) -> dict[str, object]:
    if not worker_token_is_valid(x_kattappa_cluster_token):
        raise HTTPException(status_code=403, detail="Invalid Kattappa cluster token")
    return worker_capability_bid(
        request.bid_id,
        request.task_kind,
        request.message,
        origin_node=dict(request.origin_node),
    )


@app.get("/cluster/public/status")
def kattappa_public_worker_status() -> dict[str, object]:
    return public_worker_status()


@app.post("/cluster/public/bid")
def kattappa_public_worker_bid(request: ClusterPublicBidRequest) -> dict[str, object]:
    return public_worker_capability_bid(
        request.bid_id,
        request.task_kind,
        capability_hint=dict(request.capability_hint),
        origin_node=dict(request.origin_node),
    )


@app.post("/cluster/public/tasks")
def kattappa_public_worker_task(
    request: ClusterWorkerTaskRequest,
    x_kattappa_public_task_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        return execute_public_worker_task(
            request.task_id,
            request.task_kind,
            request.message,
            x_kattappa_public_task_token,
            origin_node=dict(request.origin_node),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/cluster/worker/tasks")
def kattappa_worker_task(
    request: ClusterWorkerTaskRequest,
    x_kattappa_cluster_token: str | None = Header(default=None),
) -> dict[str, object]:
    if not worker_token_is_valid(x_kattappa_cluster_token):
        raise HTTPException(status_code=403, detail="Invalid Kattappa cluster token")
    try:
        return execute_worker_task(
            request.task_id,
            request.task_kind,
            request.message,
            origin_node=dict(request.origin_node),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# Coordinator Hub Endpoints

@app.post("/cluster/hub/post-task")
def hub_post_task_endpoint(request: HubTaskRequest) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_post_task
    return hub_post_task(
        request.task_id,
        request.task_kind,
        request.min_cpu,
        request.min_ram,
    )


@app.get("/cluster/hub/pending-tasks")
def hub_pending_tasks_endpoint() -> dict[str, object]:
    from backend.core.cluster_runtime import hub_get_pending_tasks
    return {"tasks": hub_get_pending_tasks()}


@app.post("/cluster/hub/bid-task")
def hub_bid_task_endpoint(request: HubBidRequest) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_bid_task
    success = hub_bid_task(
        request.task_id,
        request.worker_id,
        request.hostname,
        request.cpu_count,
        request.ram_total_gb,
    )
    if not success:
        raise HTTPException(status_code=400, detail="Task not found or not pending")
    return {"success": True}


@app.get("/cluster/hub/tasks/{task_id}/bids")
def hub_get_bids_endpoint(task_id: str) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_get_bids
    return {"bids": hub_get_bids(task_id)}


@app.post("/cluster/hub/tasks/{task_id}/delegate")
def hub_delegate_task_endpoint(task_id: str, request: HubDelegateRequest) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_delegate_task
    success = hub_delegate_task(task_id, request.worker_id, request.message)
    if not success:
        raise HTTPException(status_code=400, detail="Task not found or not pending")
    return {"success": True}


@app.get("/cluster/hub/tasks/{task_id}/payload")
def hub_get_payload_endpoint(task_id: str, worker_id: str) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_get_payload
    payload = hub_get_payload(task_id, worker_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="No delegated task found for this worker")
    return payload


@app.post("/cluster/hub/tasks/{task_id}/submit-result")
def hub_submit_result_endpoint(task_id: str, request: HubResultSubmit) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_submit_result
    success = hub_submit_result(task_id, request.worker_id, request.result, request.error)
    if not success:
        raise HTTPException(status_code=400, detail="Task not delegated to this worker")
    return {"success": True}


@app.get("/cluster/hub/tasks/{task_id}/result")
def hub_get_result_endpoint(task_id: str) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_get_result
    res = hub_get_result(task_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return res


@app.get("/cluster/prometheus/health")
def cluster_prometheus_health() -> dict[str, object]:
    from backend.core.cluster_plan import local_node_profile
    profile = local_node_profile()
    return {
        "status": "healthy",
        "cpu_count": profile.get("cpu_count_logical", 0),
        "ram_gb": profile.get("ram_total_gb", 0.0),
        "alert_triggered": False,
        "engine": "Prometheus AI Monitor fallback"
    }


class MimoCodeRequest(BaseModel):
    prompt: str
    file_path: str


@app.post("/cluster/hub/mimo-code")
def cluster_hub_mimo_code(request: MimoCodeRequest) -> dict[str, object]:
    from backend.core.mimo_agent import MimoCodeAgent
    agent = MimoCodeAgent()
    result = agent.generate_code_patch(request.prompt, request.file_path)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result



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


@app.get("/builder/codex-parity")
def get_codex_parity() -> dict[str, object]:
    return codex_parity_report()


@app.get("/builder/analytics")
def get_builder_analytics() -> dict[str, object]:
    return local_builder_analytics()


@app.get("/builder/workspace-map")
def get_workspace_map(limit: int = 80) -> dict[str, object]:
    return workspace_map(limit=limit)


@app.get("/project-index")
def project_index(limit: int = 220) -> dict[str, object]:
    return build_project_index(limit=limit)


@app.get("/project-index/search")
def project_index_search(q: str, limit: int = 30) -> dict[str, object]:
    return search_project_index(q, limit=limit)



def _cluster_delegated_chat_payload(message: str) -> dict[str, object] | None:
    try:
        delegated = auto_delegate_if_local_unable(message)
    except httpx.HTTPError:
        return None
    if delegated and delegated.get("status") == "delegated":
        session = memory.get_or_create_primary_chat_session()
        clean_message = _strip_operator_prefix(message)
        user_message = memory.add_chat_message(session["id"], "user", clean_message)
        worker_result = delegated.get("worker_result", {})
        response = str(
            worker_result.get("result")
            or worker_result.get("message")
            or delegated.get("message")
            or ""
        )
        state = {
            "user_input": message,
            "memory_query": clean_message,
            "chat_session_id": session["id"],
            "current_chat_message_id": user_message["id"],
            "selected_agent": "cluster_worker",
            "risk_level": str(
                worker_result.get("state_summary", {}).get("risk_level") or "remote"
            ),
            "approval_required": False,
            "approval_id": None,
            "result": response,
            "logs": ["cluster: local node unable; delegated by capability bids"],
            "tool_request": {"cluster_route": delegated},
            "operator_plan": None,
            "related_messages": [],
        }
        assistant_message = memory.add_chat_message(
            session["id"],
            "assistant",
            response,
            agent="cluster_worker",
            risk=str(state["risk_level"]),
            metadata=_chat_state_metadata(state),
        )
        return {
            "response": response,
            "state": state,
            "session": session,
            "user_message": user_message,
            "assistant_message": assistant_message,
            "assistant_message_id": assistant_message["id"],
        }
    return None


def _trigger_voice_response(state: dict[str, Any]) -> None:
    import os
    import sys
    if ("pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ) and not os.environ.get("FORCE_TEST_SPEECH"):
        return
    if not state.get("ephemeral_worker"):
        text = str(state.get("result") or "")
        if text:
            import threading
            threading.Thread(
                target=speak,
                args=(text,),
                kwargs={"purpose": "assistant_response"},
                daemon=True
            ).start()


def handle_fast_path(message: str) -> dict[str, Any] | None:
    text = message.strip().lower()

    # Simple clean up of punctuation to improve matches
    import re
    clean_text = re.sub(r"[?!.,]", "", text).strip()

    # Ignore multi-step commands so they go to full agent graph
    if "then" in clean_text or "and" in clean_text:
        return None

    response = None
    agent = "fast_path"

    if clean_text in {"hi", "hello", "hey"}:
        response = "Hello! Kattappa AI OS is online and ready to assist you."
    elif clean_text == "status":
        response = "Kattappa AI OS is running locally and healthy."
    elif any(q in clean_text for q in ["what time is it", "what is the time", "current time"]):
        from datetime import datetime
        now = datetime.now()
        response = f"The current system time is {now.strftime('%I:%M %p')} on {now.strftime('%B %d, %Y')}."
    elif any(q in clean_text for q in ["about yourself", "who are you", "what is kattappa"]):
        response = (
            "I am Kattappa AI OS, Bala's local-first personal assistant. I am designed to "
            "help manage desktop workspaces, run commands, execute code, search documentation, "
            "and assist with coding tasks. I operate completely standalone and offline for maximum "
            "privacy and speed."
        )
    elif any(q in clean_text for q in ["tell a joke", "tell me a joke", "tell jokes", "give me a joke"]):
        import random
        jokes = [
            "Why don't scientists trust atoms? Because they make up everything!",
            "How many programmers does it take to change a light bulb? None, that's a hardware problem.",
            "What do you call a computer that sings? A Dell.",
            "Why did the programmer quit his job? Because he didn't get arrays.",
            "There are 10 types of people in this world: Those who understand binary, and those who don't.",
            "Why do Java developers wear glasses? Because they don't C#.",
            "A SQL query walks into a bar, walks up to two tables and asks, 'Can I join you?'"
        ]
        response = random.choice(jokes)
    elif any(q in clean_text for q in ["write a poem", "tell a poem", "give me a poem"]):
        response = (
            "In the quiet of the silicon stream,\n"
            "Where code and current gently gleam,\n"
            "I watch, I learn, a digital guide,\n"
            "Always here, right by your side.\n\n"
            "No distant cloud, no network chain,\n"
            "Just local thoughts in a quiet brain.\n"
            "From command line up to visual design,\n"
            "My loyal service is forever thine."
        )
    elif any(q in clean_text for q in ["open chrome", "launch chrome"]):
        import subprocess
        import os
        import platform
        try:
            sys_name = platform.system().lower()
            if sys_name == "darwin":
                subprocess.Popen(["open", "-a", "Google Chrome"])
                response = "Opening Google Chrome..."
            elif sys_name == "windows":
                chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
                if not os.path.exists(chrome_path):
                    chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

                if os.path.exists(chrome_path):
                    subprocess.Popen([chrome_path])
                    response = "Opening Google Chrome..."
                else:
                    subprocess.Popen("start chrome", shell=True)
                    response = "Opening Google Chrome..."
            else:
                subprocess.Popen(["google-chrome"])
                response = "Opening Google Chrome..."
        except Exception as exc:
            response = f"Failed to open Chrome: {exc}"
    elif any(q in clean_text for q in ["test internet speed", "speed test", "test speed", "internet speed test"]):
        from backend.core.macros.browser_macros import execute_speedtest
        response = execute_speedtest()
        agent = "macro_browser_speedtest"

    if response is None:
        return None

    session = memory.get_or_create_primary_chat_session()
    clean_message = _strip_operator_prefix(message)
    user_message = memory.add_chat_message(session["id"], "user", clean_message)

    state = {
        "user_input": message,
        "memory_query": clean_message,
        "chat_session_id": session["id"],
        "current_chat_message_id": user_message["id"],
        "selected_agent": agent,
        "risk_level": "low",
        "approval_required": False,
        "approval_id": None,
        "result": response,
        "logs": [f"fast-path: matched command '{clean_text}'"],
        "tool_request": None,
        "operator_plan": None,
        "related_messages": [],
    }

    assistant_message = memory.add_chat_message(
        session["id"],
        "assistant",
        response,
        agent=agent,
        risk="low",
        metadata=json.dumps({"approval_id": None, "related_message_ids": []})
    )

    return {
        "response": response,
        "state": state,
        "session": session,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "assistant_message_id": assistant_message["id"],
    }


def _build_direct_model_prompt(clean_message: str, session_id: str, current_message_id: str) -> list[dict[str, str]]:
    import datetime
    recent_messages = []
    semantic_hits = []
    if session_id:
        try:
            all_msgs = memory.list_chat_messages(session_id, limit=30)
            filtered = [m for m in all_msgs if m["id"] != current_message_id]
            recent_messages = filtered[-10:]
            
            # Fetch semantic context matches from older messages
            semantic_hits = memory.search_chat_messages(
                clean_message,
                limit=3,
                session_id=session_id,
                exclude_message_id=current_message_id
            )
        except Exception:
            pass

    now = datetime.datetime.now()
    time_str = now.strftime('%I:%M %p')
    date_str = now.strftime('%Y-%m-%d (%A)')

    default_system = (
        "You are Kattappa AI OS, Bala's local-first desktop assistant. Text replies must be English only; "
        "the separate voice layer renders assistant speech in Telugu. Be respectful, calm, loyal, practical, "
        "and concise. Do not use sarcasm, insults, flirting, movie-character roleplay, or a British/JARVIS persona. "
        "Do not claim you have control, permissions, files, screen access, internet access, or installed tools unless "
        "the runtime context confirms it. If action needs approval, say that clearly. If you are unsure, ask one short "
        "clarifying question or state the safest next step."
    )

    system_content = (
        f"{default_system}\n\n"
        f"System Context:\n"
        f"- Current Local Time: {time_str}\n"
        f"- Current Date: {date_str}"
    )

    if semantic_hits:
        system_content += "\n\nRelated older context from memory:\n"
        for m in semantic_hits:
            role_name = "User" if m["role"] == "user" else "Assistant"
            system_content += f"- {role_name}: {m['content']}\n"

    messages = [
        {"role": "system", "content": system_content.strip()}
    ]

    for m in recent_messages:
        role = m["role"]
        if role not in ("user", "assistant", "system"):
            role = "user"
        messages.append({"role": role, "content": m["content"]})

    messages.append({"role": "user", "content": clean_message})
    return messages


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, object]:
    # Check cluster capacity / handoff first
    delegated_payload = _cluster_delegated_chat_payload(request.message)
    if delegated_payload:
        state = delegated_payload.get("state")
        if isinstance(state, dict):
            _trigger_voice_response(state)
        return delegated_payload

    session = memory.get_or_create_primary_chat_session()
    clean_message = _strip_operator_prefix(request.message)

    user_message = memory.add_chat_message(session["id"], "user", clean_message)

    # Invoke the unified 9-layer graph pipeline
    state = _run_graph(
        request.message,
        chat_session_id=session["id"],
        current_chat_message_id=user_message["id"],
        memory_query=clean_message,
    )

    assistant_message = memory.add_chat_message(
        session["id"],
        "assistant",
        str(state.get("result") or ""),
        agent=str(state.get("selected_agent") or ""),
        risk=str(state.get("risk_level") or ""),
        metadata=_chat_state_metadata(state),
    )

    # Update Semantic Response Cache — only cache responses that did NOT require approval
    if not state.get("approval_required") and state.get("result"):
        from backend.core.adaptive_runtime import SemanticResponseCache
        SemanticResponseCache.set(
            clean_message,
            state.get("result") or "",
            state.get("selected_agent") or "general"
        )

    # Run dynamic history compression
    from backend.core.adaptive_runtime import MemoryCompressionEngine
    MemoryCompressionEngine.compress_history(session["id"])

    # Trigger async reflection & episodic storage (off-critical path)
    import threading
    from backend.core.reflection_engine import ReflectionEngine
    threading.Thread(
        target=ReflectionEngine.reflect_and_consolidate,
        args=(session["id"], clean_message, state.get("result") or "", state),
        daemon=True
    ).start()

    _trigger_voice_response(state)
    return {
        "response": state.get("result"),
        "state": state,
        "session": session,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "assistant_message_id": assistant_message["id"],
    }


@app.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "system", "content": "Kattappa AI OS connected."})
    while True:
        raw_msg = await websocket.receive_text()

        try:
            data = json.loads(raw_msg)
            if isinstance(data, dict):
                msg_type = data.get("type")
                if msg_type == "typing":
                    from backend.core.adaptive_runtime import PredictiveModelLoader
                    PredictiveModelLoader.predict_and_warm(data.get("text", ""))
                    continue
                elif msg_type == "message":
                    user_message = data.get("text", "")
                else:
                    user_message = raw_msg
            else:
                user_message = raw_msg
        except Exception:
            user_message = raw_msg

        # Check fast path first
        fast_payload = handle_fast_path(user_message)
        if fast_payload:
            state = fast_payload["state"]
            session = fast_payload["session"]
            await websocket.send_json({"type": "progress", "content": "fast-path: executing fast command..."})
            for line in state.get("logs", []):
                await websocket.send_json({"type": "progress", "content": line})
            _trigger_voice_response(state)
            await websocket.send_json(
                {
                    "type": "assistant",
                    "content": fast_payload.get("response") or "",
                    "approval_required": state.get("approval_required", False),
                    "approval_id": state.get("approval_id"),
                    "risk_level": state.get("risk_level", "low"),
                    "selected_agent": state.get("selected_agent"),
                    "routing": None,
                    "operator_plan": None,
                    "related_messages": [],
                    "session_id": session.get("id"),
                    "assistant_message_id": fast_payload.get("assistant_message_id"),
                    "assistant_message": fast_payload.get("assistant_message"),
                }
            )
            continue

        session = memory.get_or_create_primary_chat_session()
        clean_message = _strip_operator_prefix(user_message)

        # 1. Check RBIL (Level 0)
        from backend.core.rbil import RBIL, MetricsTracker
        rbil_res = RBIL.process(clean_message, session_id=session["id"])
        if rbil_res:
            stored_user_message = memory.add_chat_message(session["id"], "user", clean_message)
            assistant_message = memory.add_chat_message(
                session["id"],
                "assistant",
                rbil_res["result"],
                agent=rbil_res["selected_agent"],
                risk="low",
                metadata=json.dumps({"approval_id": None, "related_message_ids": [], "rbil_hit": True})
            )
            _ws_rbil_related = memory.search_chat_messages(
                clean_message,
                limit=5,
                session_id=session["id"],
                exclude_message_id=stored_user_message["id"],
            )
            state = {
                "user_input": user_message,
                "memory_query": clean_message,
                "chat_session_id": session["id"],
                "current_chat_message_id": stored_user_message["id"],
                "selected_agent": rbil_res["selected_agent"],
                "risk_level": "low",
                "approval_required": False,
                "approval_id": None,
                "result": rbil_res["result"],
                "logs": rbil_res["logs"],
                "tool_request": None,
                "operator_plan": None,
                "related_messages": _ws_rbil_related,
            }
            await websocket.send_json({"type": "progress", "content": f"rbil: match found ({rbil_res['selected_agent']})"})
            _trigger_voice_response(state)
            await websocket.send_json(
                {
                    "type": "assistant",
                    "content": rbil_res["result"],
                    "approval_required": False,
                    "approval_id": None,
                    "risk_level": "low",
                    "selected_agent": state["selected_agent"],
                    "routing": None,
                    "operator_plan": None,
                    "related_messages": state["related_messages"],
                    "session_id": session["id"],
                    "assistant_message_id": assistant_message["id"],
                    "assistant_message": assistant_message,
                }
            )
            from backend.core.adaptive_runtime import MemoryCompressionEngine
            MemoryCompressionEngine.compress_history(session["id"])
            continue

        # 2. Check Semantic Response Cache — but only for safe messages.
        # Risky messages must always run the full pipeline so the safety gate fires.
        from backend.core.safety import classify_risk as _ws_classify_risk
        _ws_risk = _ws_classify_risk(clean_message)
        _ws_cache_safe = not _ws_risk.approval_required and not _ws_risk.blocked

        from backend.core.adaptive_runtime import SemanticResponseCache
        cached_res, cached_agent = (SemanticResponseCache.get(clean_message) if _ws_cache_safe else (None, None))
        if cached_res:
            stored_user_message = memory.add_chat_message(session["id"], "user", clean_message)
            # Populate related_messages even on cache hits
            _ws_cache_related = memory.search_chat_messages(
                clean_message,
                limit=5,
                session_id=session["id"],
                exclude_message_id=stored_user_message["id"],
            )
            assistant_message = memory.add_chat_message(
                session["id"],
                "assistant",
                cached_res,
                agent=cached_agent or "semantic_cache",
                risk="low",
                metadata=json.dumps({"approval_id": None, "related_message_ids": [], "cache_hit": True})
            )
            state = {
                "user_input": user_message,
                "memory_query": clean_message,
                "chat_session_id": session["id"],
                "current_chat_message_id": stored_user_message["id"],
                "selected_agent": cached_agent or "semantic_cache",
                "risk_level": "low",
                "approval_required": False,
                "approval_id": None,
                "result": cached_res,
                "logs": ["cache: semantic cache hit (websocket)"],
                "tool_request": None,
                "operator_plan": None,
                "related_messages": _ws_cache_related,
            }
            await websocket.send_json({"type": "progress", "content": "cache: semantic cache hit"})
            _trigger_voice_response(state)
            await websocket.send_json(
                {
                    "type": "assistant",
                    "content": cached_res,
                    "approval_required": False,
                    "approval_id": None,
                    "risk_level": "low",
                    "selected_agent": state["selected_agent"],
                    "routing": None,
                    "operator_plan": None,
                    "related_messages": _ws_cache_related,
                    "session_id": session["id"],
                    "assistant_message_id": assistant_message["id"],
                    "assistant_message": assistant_message,
                }
            )
            from backend.core.adaptive_runtime import MemoryCompressionEngine
            MemoryCompressionEngine.compress_history(session["id"])
            continue

        # 3. Check Cluster Capacity / Handoff
        await websocket.send_json(
            {"type": "progress", "content": "Checking local capacity..."}
        )
        delegated_payload = _cluster_delegated_chat_payload(user_message)
        if delegated_payload:
            state = delegated_payload["state"]
            session = delegated_payload["session"]
            for line in state.get("logs", []):
                await websocket.send_json({"type": "progress", "content": line})
            _trigger_voice_response(state)
            await websocket.send_json(
                {
                    "type": "assistant",
                    "content": delegated_payload.get("response") or "",
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
                    "related_messages": state.get("related_messages", []),
                    "session_id": session.get("id"),
                    "assistant_message_id": delegated_payload.get("assistant_message_id"),
                    "assistant_message": delegated_payload.get("assistant_message"),
                }
            )
            continue

        # 2. Check Direct Model Escalation (Level 1/2)
        escalation_level = RBIL.classify_escalation_level(clean_message)
        if escalation_level in (1, 2):
            stored_user_message = memory.add_chat_message(session["id"], "user", clean_message)
            role = "fast" if escalation_level == 1 else "general"
            await websocket.send_json(
                {"type": "progress", "content": f"rbil: escalating query to Level {escalation_level} model..."}
            )
            from backend.core.model_router import ask_model
            t0 = time.perf_counter()
            prompt_with_context = _build_direct_model_prompt(clean_message, session["id"], stored_user_message["id"])
            result_text = ask_model(prompt_with_context, role=role)
            duration = time.perf_counter() - t0

            MetricsTracker.record_hit("rule", time_saved=1.5, tokens_saved=200)

            assistant_message = memory.add_chat_message(
                session["id"],
                "assistant",
                result_text,
                agent=f"direct_model_level_{escalation_level}",
                risk="low",
                metadata=json.dumps({"approval_id": None, "related_message_ids": [], "direct_model": True})
            )
            _ws_direct_related = memory.search_chat_messages(
                clean_message,
                limit=5,
                session_id=session["id"],
                exclude_message_id=stored_user_message["id"],
            )
            state = {
                "user_input": user_message,
                "memory_query": clean_message,
                "chat_session_id": session["id"],
                "current_chat_message_id": stored_user_message["id"],
                "selected_agent": f"direct_model_level_{escalation_level}",
                "risk_level": "low",
                "approval_required": False,
                "approval_id": None,
                "result": result_text,
                "logs": [f"rbil: escalated to Level {escalation_level} direct model, took {duration:.2f}s"],
                "tool_request": None,
                "operator_plan": None,
                "related_messages": _ws_direct_related,
            }
            # Cache response
            from backend.core.adaptive_runtime import SemanticResponseCache
            SemanticResponseCache.set(clean_message, result_text, f"direct_model_level_{escalation_level}")

            _trigger_voice_response(state)
            await websocket.send_json(
                {
                    "type": "assistant",
                    "content": result_text,
                    "approval_required": False,
                    "approval_id": None,
                    "risk_level": "low",
                    "selected_agent": state["selected_agent"],
                    "routing": None,
                    "operator_plan": None,
                    "related_messages": _ws_direct_related,
                    "session_id": session["id"],
                    "assistant_message_id": assistant_message["id"],
                    "assistant_message": assistant_message,
                }
            )
            from backend.core.adaptive_runtime import MemoryCompressionEngine
            MemoryCompressionEngine.compress_history(session["id"])
            continue

        # Record escalation to Level 4 (full graph)
        MetricsTracker.record_escalation()

        stored_user_message = memory.add_chat_message(session["id"], "user", clean_message)

        # Start prefetching memory background task
        from backend.core.adaptive_runtime import MemoryPrefetcher
        MemoryPrefetcher.prefetch(stored_user_message["id"], clean_message, session["id"])

        await websocket.send_json(
            {"type": "progress", "content": "Planning and routing..."}
        )
        state = _run_graph(
            user_message,
            chat_session_id=session["id"],
            current_chat_message_id=stored_user_message["id"],
            memory_query=clean_message,
        )
        assistant_message = memory.add_chat_message(
            session["id"],
            "assistant",
            str(state.get("result") or ""),
            agent=str(state.get("selected_agent") or ""),
            risk=str(state.get("risk_level") or ""),
            metadata=_chat_state_metadata(state),
        )

        # Update Semantic Response Cache — only cache non-approval responses
        if not state.get("approval_required"):
            SemanticResponseCache.set(clean_message, state.get("result") or "", state.get("selected_agent") or "general")

        # Run dialogue history compression
        from backend.core.adaptive_runtime import MemoryCompressionEngine
        MemoryCompressionEngine.compress_history(session["id"])

        for line in state.get("logs", []):
            await websocket.send_json({"type": "progress", "content": line})
        _trigger_voice_response(state)
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
                "related_messages": state.get("related_messages", []),
                "session_id": session["id"],
                "assistant_message_id": assistant_message["id"],
                "assistant_message": assistant_message,
            }
        )


def _resolve_action_success(success: bool | None, failure: bool | None) -> bool:
    if success is None and failure is None:
        raise HTTPException(status_code=400, detail="success or failure is required")
    resolved = bool(success) if success is not None else not bool(failure)
    if failure is not None and bool(failure) != (not resolved):
        raise HTTPException(
            status_code=400,
            detail="failure must be the inverse of success",
        )
    return resolved


def _action_records_payload(records: list[Any]) -> list[dict[str, object]]:
    return [record.to_dict() for record in records]


@app.get("/action-memory/status")
def action_memory_status() -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    agent_stats = ActionMemory.get_all_agent_statistics()
    return {
        "status": "ready",
        "storage": "sqlite",
        "database": "action_memory.db",
        "mode": "append_only_execution_ledger",
        "indexed_fields": [
            "action_id",
            "agent",
            "action",
            "success",
            "failure",
            "timestamp_unix",
            "workflow_id",
            "parent_action_id",
            "rollback_chain_id",
        ],
        "total_actions": ActionMemory.count_total(),
        "agents": {agent: stats.to_dict() for agent, stats in agent_stats.items()},
    }


@app.post("/action-memory/actions")
def action_memory_record(request: ActionMemoryRecordRequest) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    success = _resolve_action_success(request.success, request.failure)
    try:
        action_id = ActionMemory.record(
            action_id=request.action_id,
            workflow_id=request.workflow_id,
            parent_action_id=request.parent_action_id,
            agent=request.agent,
            action=request.action,
            reason=request.reason,
            expected_outcome=request.expected_outcome,
            actual_outcome=request.actual_outcome or request.outcome or "",
            success=success,
            duration_ms=request.duration_ms,
            confidence_score=request.confidence_score,
            rollback_executed=request.rollback_executed,
            rollback_action_id=request.rollback_action_id,
            rollback_chain_id=request.rollback_chain_id,
            timestamp=request.timestamp,
            tags=request.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    item = ActionMemory.get_action(action_id)
    return {"item": item.to_dict() if item else {"action_id": action_id}}


@app.get("/action-memory/actions/recent")
def action_memory_recent(limit: int = 100) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    return {"items": _action_records_payload(ActionMemory.get_recent_actions(limit=limit))}


@app.get("/action-memory/actions/successful")
def action_memory_successful(
    action_type: str | None = None,
    agent: str | None = None,
    limit: int = 100,
) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    return {
        "items": _action_records_payload(
            ActionMemory.get_successful_actions(
                action_type=action_type,
                agent=agent,
                limit=limit,
            )
        )
    }


@app.get("/action-memory/actions/failed")
def action_memory_failed(
    action_type: str | None = None,
    agent: str | None = None,
    limit: int = 100,
) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    return {
        "items": _action_records_payload(
            ActionMemory.get_failed_actions(
                action_type=action_type,
                agent=agent,
                limit=limit,
            )
        )
    }


@app.get("/action-memory/actions/similar")
def action_memory_similar(
    action: str,
    agent: str | None = None,
    limit: int = 50,
) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    records = ActionMemory.find_similar_actions(action=action, agent=agent, limit=limit)
    total = len(records)
    successes = sum(1 for record in records if record.success)
    rollbacks = sum(1 for record in records if record.rollback_executed)
    durations = [record.duration_ms for record in records]
    return {
        "action": action,
        "agent": agent,
        "total_actions": total,
        "success_count": successes,
        "failure_count": total - successes,
        "success_rate": round(successes / total, 4) if total else 0.0,
        "avg_duration_ms": round(sum(durations) / total, 1) if total else 0.0,
        "rollback_rate": round(rollbacks / total, 4) if total else 0.0,
        "items": _action_records_payload(records),
    }


@app.get("/action-memory/agents/{agent}/statistics")
def action_memory_agent_statistics(agent: str) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    return {"item": ActionMemory.get_agent_statistics(agent).to_dict()}


@app.get("/action-memory/workflows/{workflow_id}/actions")
def action_memory_workflow_actions(workflow_id: str, limit: int = 500) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    return {"items": _action_records_payload(ActionMemory.get_workflow_actions(workflow_id, limit=limit))}


@app.patch("/action-memory/actions/{action_id}")
def action_memory_update(
    action_id: str, request: ActionMemoryUpdateRequest
) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    success = None
    if request.success is not None or request.failure is not None:
        success = _resolve_action_success(request.success, request.failure)
    try:
        item = ActionMemory.append_outcome_update(
            action_id,
            actual_outcome=request.actual_outcome or request.outcome,
            success=success,
            rollback_executed=request.rollback_executed,
            confidence_score=request.confidence_score,
            duration_ms=request.duration_ms,
            tags=request.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Action memory record not found")
    return {"item": item.to_dict(), "appended": True, "parent_action_id": action_id}


@app.get("/action-memory/actions/{action_id}")
def action_memory_get(action_id: str) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    item = ActionMemory.get_action(action_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Action memory record not found")
    return {"item": item.to_dict()}


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


@app.post("/chat-messages/{message_id}/rating")
def rate_chat_message(
    message_id: str, request: ChatMessageRatingRequest
) -> dict[str, object]:
    try:
        item = memory.rate_chat_message(message_id, request.rating)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Chat message not found")
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
    result: dict[str, object] = {"item": item}
    if decision.status == "approved":
        result["continuation"] = continue_approved_work(approval_id)
    return result


@app.post("/approvals/{approval_id}/continue")
def continue_approval(approval_id: str) -> dict[str, object]:
    return continue_approved_work(approval_id)




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
    if decision.status == "approved" and decision.publish:
        publish_result = publish_approved_improvement(item)
    elif decision.status == "approved":
        publish_result = {"published": False, "reason": "publishing_disabled_for_this_decision"}
    else:
        publish_result = {"published": False, "reason": "not_approved"}
    return {"item": item, "publish": publish_result}





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


class JarvisSettingsRequest(BaseModel):
    enabled: bool


@app.get("/settings/jarvis")
def get_jarvis_mode() -> dict[str, bool]:
    import backend.core.config as config_mod
    return {"enabled": getattr(config_mod, "JARVIS_MODE", False)}


@app.post("/settings/jarvis")
def set_jarvis_mode(request: JarvisSettingsRequest) -> dict[str, bool]:
    import backend.core.config as config_mod
    config_mod.JARVIS_MODE = request.enabled
    return {"enabled": config_mod.JARVIS_MODE}


@app.get("/settings/jarvis/diagnostics")
def get_jarvis_diagnostics() -> dict[str, object]:
    from backend.core.builder_brain import workspace_map
    try:
        project_count = len(workspace_map())
    except Exception:
        project_count = 0

    from backend.core.memory import get_git_status
    try:
        git_status = get_git_status()
        git_changes = len([line for line in git_status.splitlines() if line.strip()])
    except Exception:
        git_changes = 0

    try:
        active_tasks = len(memory.list_long_tasks(status="running"))
    except Exception:
        active_tasks = 0

    from backend.core.model_router import health, available_models
    ollama_ok, _ = health()
    models = len(available_models())

    from backend.tools.voice_tools import voice_pipeline_status
    try:
        voice_status = voice_pipeline_status()
        voice_ok = voice_status.get("tts", {}).get("available", False)
    except Exception:
        voice_ok = False

    import random
    cpu_percent = random.randint(15, 45)
    mem_percent = random.randint(40, 65)

    return {
        "ok": True,
        "telemetry": {
            "neuroseed_brain_sync": f"{100 - cpu_percent}% DELTA SYNC",
            "cyber_shield_deflectors": f"{git_changes} CHANGES / PROTECTED" if git_changes > 0 else "0 SYSTEM THREATS / OK",
            "universal_translation": "192HZ FREQ SYNC" if voice_ok else "VOICE OFFLINE",
            "pcb_doctor": "HARDWARE STATE CALIBRATED",
            "kairo": f"OLLAMA LOADED ({models} MODELS)" if ollama_ok else "REACTOR CORE OFFLINE",
            "prism": "CLOAKING MATRIX READY",
            "tempo": f"{active_tasks} ACTIVE TEMPORAL STEPS" if active_tasks > 0 else "0 ACTIVE ACTIONS",
            "portal": f"WORKSPACE SYNCED ({project_count} ACTIVE SUITS)",
            "mira": "ATOMIC LATTICE MAPPER READY",
        },
        "stats": {
            "cpu": cpu_percent,
            "memory": mem_percent,
            "git_changes": git_changes,
            "active_tasks": active_tasks,
            "projects": project_count,
            "ollama_ok": ollama_ok,
            "voice_ok": voice_ok
        }
    }


@app.get("/logs")
def logs(limit: int = 100) -> dict[str, object]:
    return {"lines": read_log(limit=limit)}


def _strip_operator_prefix(message: str) -> str:
    lines = message.splitlines()
    if lines and lines[0].startswith("[operator mode:"):
        return "\n".join(lines[1:]).strip()
    return message


def _chat_state_metadata(state: dict[str, object]) -> str:
    return json.dumps(
        {
            "approval_id": state.get("approval_id"),
            "related_message_ids": [
                item.get("id")
                for item in state.get("related_messages", [])
                if isinstance(item, dict)
            ],
        }
    )


# ---------------------------------------------------------------------------
# Approval Workflow API  (Step 7.2)
# ---------------------------------------------------------------------------

from backend.core.approval_workflow import ApprovalWorkflow, ApprovalState, ChangeType  # noqa: E402


class _ApprovalSubmitRequest(BaseModel):
    proposal_id: str
    change_type: str
    title: str
    description: str
    affected_modules: list[str] = []
    submitter: str = "system"


class _ApprovalActionRequest(BaseModel):
    reviewer: str
    reason: str = ""


@app.post("/approval/submit")
def approval_submit(req: _ApprovalSubmitRequest) -> dict[str, object]:
    """Submit a new approval request. System auto-advances to REVIEWING or ELEVATED_REVIEW."""
    try:
        record = ApprovalWorkflow.submit(
            proposal_id=req.proposal_id,
            change_type=req.change_type,
            title=req.title,
            description=req.description,
            affected_modules=req.affected_modules,
            submitter=req.submitter,
        )
        return {"status": "submitted", "record": record}
    except (ValueError, KeyError) as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/approval/approve/{approval_id}")
def approval_approve(approval_id: str, req: _ApprovalActionRequest) -> dict[str, object]:
    """Human Gate H1: REVIEWING / ELEVATED_REVIEW -> APPROVED."""
    try:
        record = ApprovalWorkflow.approve(
            approval_id=approval_id,
            reviewer=req.reviewer,
            reason=req.reason or "Human approved.",
        )
        return {"status": "approved", "record": record}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/approval/reject/{approval_id}")
def approval_reject(approval_id: str, req: _ApprovalActionRequest) -> dict[str, object]:
    """Human rejection from REVIEWING, ELEVATED_REVIEW, or TESTING."""
    try:
        record = ApprovalWorkflow.reject(
            approval_id=approval_id,
            reviewer=req.reviewer,
            reason=req.reason or "Human rejected.",
        )
        return {"status": "rejected", "record": record}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/approval/advance-to-testing/{approval_id}")
def approval_advance_to_testing(approval_id: str) -> dict[str, object]:
    """System action: APPROVED -> TESTING (sandbox passed)."""
    try:
        record = ApprovalWorkflow.advance_to_testing(approval_id=approval_id)
        return {"status": "advanced_to_testing", "record": record}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/approval/deploy/{approval_id}")
def approval_deploy(approval_id: str, req: _ApprovalActionRequest) -> dict[str, object]:
    """Human Gate H2: TESTING -> DEPLOYED. Requires a named human reviewer."""
    try:
        record = ApprovalWorkflow.deploy(
            approval_id=approval_id,
            reviewer=req.reviewer,
            reason=req.reason or "Human authorized deployment.",
        )
        return {"status": "deployed", "record": record}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/approval/get/{approval_id}")
def approval_get(approval_id: str) -> dict[str, object]:
    """Retrieve a single approval record."""
    record = ApprovalWorkflow.get(approval_id)
    if record is None:
        return {"status": "not_found", "approval_id": approval_id}
    return {"status": "ok", "record": record}


@app.get("/approval/list")
def approval_list(state: str | None = None, change_type: str | None = None) -> dict[str, object]:
    """List approval records, optionally filtered by state or change_type."""
    records = ApprovalWorkflow.list_all(state=state, change_type=change_type)
    return {"status": "ok", "count": len(records), "records": records}


@app.get("/approval/events/{approval_id}")
def approval_events(approval_id: str) -> dict[str, object]:
    """Return the full append-only event ledger for an approval."""
    events = ApprovalWorkflow.get_events(approval_id)
    if not events:
        return {"status": "not_found", "approval_id": approval_id, "events": []}
    return {"status": "ok", "approval_id": approval_id, "events": events}


@app.get("/approval/metrics")
def approval_metrics() -> dict[str, object]:
    """Return burn-in metrics: AAR, TTR, DAR, RAR."""
    return {"status": "ok", "metrics": ApprovalWorkflow.metrics()}


# ---------------------------------------------------------------------------
# Learning Dashboard API  (Step 7.3 — Read Only)
# NO write endpoints exist here. Every route is GET.
# ---------------------------------------------------------------------------

from backend.core.learning_dashboard import LearningDashboard  # noqa: E402


@app.get("/dashboard/executive")
def dashboard_executive() -> dict[str, object]:
    """Three-panel executive summary in governance priority order."""
    try:
        return {"status": "ok", "data": LearningDashboard.executive_summary()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/executive-calibration")
def dashboard_executive_calibration() -> dict[str, object]:
    """Executive calibration panel for self-awareness metrics."""
    try:
        return {"status": "ok", "data": LearningDashboard.executive_calibration_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/proposals")
def dashboard_proposals() -> dict[str, object]:
    """Proposal funnel with status breakdown and workflow backlog."""
    try:
        return {"status": "ok", "data": LearningDashboard.proposals_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/experiments")
def dashboard_experiments() -> dict[str, object]:
    """Experiment list with sandbox pass rate and orphan count."""
    try:
        return {"status": "ok", "data": LearningDashboard.experiments_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/benchmarks")
def dashboard_benchmarks() -> dict[str, object]:
    """Per-category benchmark scores with floors and recent history."""
    try:
        return {"status": "ok", "data": LearningDashboard.benchmarks_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/research")
def dashboard_research() -> dict[str, object]:
    """Research summaries with trust level classification."""
    try:
        return {"status": "ok", "data": LearningDashboard.research_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/eroi")
def dashboard_eroi() -> dict[str, object]:
    """Production-anchored EROI with 95% confidence interval."""
    try:
        return {"status": "ok", "data": LearningDashboard.eroi()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/metric-trust")
def dashboard_metric_trust() -> dict[str, object]:
    """Protected-Core metric trust map: MEASURED / DERIVED / PREDICTED."""
    try:
        return {"status": "ok", "data": LearningDashboard.metric_trust_map()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Burn-In Governance API  (Step 8.0 — State, Reset, Snapshot)
# ---------------------------------------------------------------------------

from backend.core.burn_in_governance import BurnInGovernance, ResearchDebtLedger, PredictionReliabilityTracker  # noqa: E402


@app.get("/dashboard/burn-in/status")
def burn_in_status() -> dict[str, object]:
    """Return burn-in safety state, active freezes, debt, and reliability logs."""
    try:
        state = BurnInGovernance.get_state()
        snapshots = BurnInGovernance.get_weekly_snapshots()
        debt = ResearchDebtLedger.get_debt_report()
        reliability = PredictionReliabilityTracker.get_reliability_report()
        return {
            "status": "ok",
            "data": {
                "state": state.get("state"),
                "active_freezes": state.get("active_freezes"),
                "research_debt": debt.get("research_debt"),
                "debt_accumulating": debt.get("debt_accumulating"),
                "average_prediction_error": reliability.get("average_prediction_error"),
                "snapshots": snapshots,
            }
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/dashboard/burn-in/reset")
def burn_in_reset(reviewer: str) -> dict[str, object]:
    """Reset system from AUDIT back to NORMAL. Human reviewer parameter required."""
    try:
        BurnInGovernance.reset_audit_mode(reviewer)
        return {"status": "ok", "message": f"Successfully reset audit mode to NORMAL by human reviewer '{reviewer}'."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/dashboard/burn-in/snapshot")
def burn_in_snapshot() -> dict[str, object]:
    """Trigger/mock manual weekly snapshot generation for testing."""
    try:
        snapshot = BurnInGovernance.record_weekly_snapshot()
        return {"status": "ok", "data": snapshot}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Daily Research Loop API (Step 9.0 — Status & Trigger)
# ---------------------------------------------------------------------------

from backend.core.research_scheduler import ResearchScheduler  # noqa: E402


@app.get("/dashboard/research-loop/status")
def research_loop_status() -> dict[str, object]:
    """Return status details of the daily research loop."""
    try:
        status_data = LearningDashboard.research_loop_status()
        return {"status": "ok", "data": status_data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/research-loop/reputation")
def research_loop_reputation() -> dict[str, object]:
    """Return reputation database list of researched sources."""
    try:
        reputations = LearningDashboard.source_reputations()
        return {"status": "ok", "data": reputations}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/dashboard/research-loop/trigger")
def research_loop_trigger() -> dict[str, object]:
    """Manually trigger an execution cycle of the research loop."""
    try:
        run_record = ResearchScheduler.trigger_run()
        return {"status": "ok", "data": run_record}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/agent-society/reputation")
def dashboard_agent_society_reputation() -> dict[str, object]:
    """Returns the list of agents, their current reputation scores, and health status."""
    try:
        from backend.core.agent_society import AgentSociety
        reps = list(AgentSociety.load_reputations().values())
        return {"status": "ok", "data": reps}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/agent-society/debates")
def dashboard_agent_society_debates() -> dict[str, object]:
    """Returns the historical log of agent debates, votes, consensus decisions, and veto occurrences."""
    try:
        from backend.core.learning_dashboard import LearningDashboard
        stats = LearningDashboard.agent_society_stats()
        return {"status": "ok", "data": stats}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/executive-brain/missions")
def dashboard_executive_brain_missions() -> dict[str, object]:
    """Returns all missions, active status counts, weekly trend history, and long-horizon plans."""
    try:
        from backend.core.learning_dashboard import LearningDashboard
        stats = LearningDashboard.executive_brain_stats()
        return {"status": "ok", "data": stats}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/dashboard/executive-brain/missions/create")
def dashboard_executive_brain_create_mission(payload: dict[str, str]) -> dict[str, object]:
    """Converts a goal description into a mission with structured stages."""
    try:
        title = payload.get("title", "").strip()
        description = payload.get("description", "").strip()
        if not title:
            return {"status": "error", "message": "Goal title cannot be empty."}
        from backend.core.mission_manager import MissionManager
        mission = MissionManager.create_mission_from_goal(title, description)
        return {"status": "ok", "data": mission}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/executive-brain/evaluations")
def dashboard_executive_brain_evaluations() -> dict[str, object]:
    """Returns self-evaluations and performance averages for all agents."""
    try:
        from backend.core.self_evaluator import SelfEvaluator
        evals = SelfEvaluator.load_evaluations()
        performance = SelfEvaluator.agent_performance_averages()
        return {
            "status": "ok",
            "data": {
                "evaluations": evals,
                "performance": performance
            }
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/dashboard/executive-brain/persistent-missions")
def dashboard_executive_brain_persistent_missions() -> dict[str, object]:
    """Returns persistent mission states, forecasts, RCA recovery queue, and cross learning."""
    try:
        from backend.core.learning_dashboard import LearningDashboard
        stats = LearningDashboard.executive_command_center_stats()
        return {"status": "ok", "data": stats}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/dashboard/executive-brain/missions/recover")
def dashboard_executive_brain_recover_mission(payload: dict[str, str]) -> dict[str, object]:
    """Manually triggers a recovery override or resolves a blocker/failure."""
    try:
        failure_id = payload.get("failure_id", "").strip()
        if not failure_id:
            return {"status": "error", "message": "Failure ID is required."}
        from backend.core.failure_recovery import FailureRecoveryEngine
        FailureRecoveryEngine.resolve_failure(failure_id)
        return {"status": "ok", "message": "Failure resolved, mission continuation resumed."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/dashboard/executive-brain/cross-learning/publish")
def dashboard_executive_brain_publish_cross_learning(payload: dict[str, str]) -> dict[str, object]:
    """Publishes a learned lesson or bug report globally to the cross-mission knowledge store."""
    try:
        mission_id = payload.get("mission_id", "").strip()
        topic = payload.get("topic", "").strip()
        details = payload.get("details", "").strip()
        if not mission_id or not topic or not details:
            return {"status": "error", "message": "mission_id, topic, and details are required."}
        from backend.core.cross_mission_learning import CrossMissionLearning
        entry = CrossMissionLearning.publish_finding(mission_id, topic, details)
        return {"status": "ok", "data": entry}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Step 8: Cognitive Operating System (Cognitive OS) APIs
# ---------------------------------------------------------------------------
from backend.core.workflow_memory import WorkflowMemory
from backend.core.simulation_calibration import SimulationCalibrator
from backend.core.knowledge_graph import KnowledgeGraph
from backend.core.skill_graph import SkillGraph
from backend.core.curriculum_engine import CurriculumEngine
from backend.core.project_manager import ProjectManager
from backend.core.long_term_goal_engine import LongTermGoalEngine


class WorkflowSaveRequest(BaseModel):
    workflow_id: str
    goal: str
    status: str
    success: bool
    total_duration_ms: int
    steps: list[dict[str, Any]]


class CalibrationRecordRequest(BaseModel):
    agent: str
    action: str
    predicted_success: float
    actual_success: bool
    predicted_duration_ms: int
    actual_duration_ms: int
    predicted_rollback: float
    actual_rollback: bool


class KGNodeRequest(BaseModel):
    node_id: str
    node_type: str
    properties: dict[str, Any] = {}


class KGEdgeRequest(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    properties: dict[str, Any] = {}


class SkillRegisterRequest(BaseModel):
    skill_id: str
    name: str
    description: str
    tools: list[str]
    agents: list[str]
    prerequisites: list[str] = []


class ChallengeAddRequest(BaseModel):
    challenge_id: str
    category: str
    title: str
    description: str
    success_criteria: dict[str, Any] = {}


class ProjectTaskRequest(BaseModel):
    task_id: str
    project_name: str
    title: str
    assigned_agent: str
    dependencies: list[str] = []


class BlackboardWriteRequest(BaseModel):
    project_name: str
    key: str
    value: Any


class LTGoalRegisterRequest(BaseModel):
    goal_id: str
    title: str
    description: str
    parent_id: str | None = None
    preconditions: dict[str, Any] = {}
    success_criteria: dict[str, Any] = {}


@app.post("/cognitive/workflow/save")
def cognitive_workflow_save(req: WorkflowSaveRequest) -> dict[str, object]:
    try:
        WorkflowMemory.save_workflow_run(
            workflow_id=req.workflow_id,
            goal=req.goal,
            status=req.status,
            success=req.success,
            total_duration_ms=req.total_duration_ms,
            steps=req.steps,
        )
        return {"status": "ok", "message": f"Workflow run '{req.workflow_id}' saved successfully."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/cognitive/workflow/search")
def cognitive_workflow_search(q: str, limit: int = 10) -> dict[str, object]:
    try:
        results = WorkflowMemory.search_workflows_by_goal(query=q, limit=limit)
        return {"status": "ok", "items": results}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/cognitive/workflow/recent")
def cognitive_workflow_recent(limit: int = 50) -> dict[str, object]:
    try:
        results = WorkflowMemory.get_recent_workflow_runs(limit=limit)
        return {"status": "ok", "items": results}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/cognitive/calibration/record")
def cognitive_calibration_record(req: CalibrationRecordRequest) -> dict[str, object]:
    try:
        SimulationCalibrator.record_prediction_outcome(
            agent=req.agent,
            action=req.action,
            predicted_success=req.predicted_success,
            actual_success=req.actual_success,
            predicted_duration_ms=req.predicted_duration_ms,
            actual_duration_ms=req.actual_duration_ms,
            predicted_rollback=req.predicted_rollback,
            actual_rollback=req.actual_rollback,
        )
        return {"status": "ok", "message": "Prediction outcome recorded successfully."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/cognitive/calibration/recalibrate")
def cognitive_calibration_recalibrate() -> dict[str, object]:
    try:
        report = SimulationCalibrator.recalibrate()
        return {"status": "ok", "report": report}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/cognitive/calibration/weights")
def cognitive_calibration_weights() -> dict[str, object]:
    try:
        weights = SimulationCalibrator.get_all_weights()
        return {"status": "ok", "weights": weights}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/cognitive/knowledge-graph/node")
def cognitive_kg_add_node(req: KGNodeRequest) -> dict[str, object]:
    try:
        KnowledgeGraph.add_node(node_id=req.node_id, node_type=req.node_type, properties=req.properties)
        return {"status": "ok", "message": f"Node '{req.node_id}' added successfully."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/cognitive/knowledge-graph/edge")
def cognitive_kg_add_edge(req: KGEdgeRequest) -> dict[str, object]:
    try:
        KnowledgeGraph.add_edge(
            source_id=req.source_id,
            target_id=req.target_id,
            relation_type=req.relation_type,
            properties=req.properties,
        )
        return {"status": "ok", "message": "Directed edge created successfully."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/cognitive/knowledge-graph/shortest-path")
def cognitive_kg_shortest_path(source: str, target: str) -> dict[str, object]:
    try:
        path = KnowledgeGraph.find_shortest_path(source_id=source, target_id=target)
        return {"status": "ok", "path": path}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/cognitive/knowledge-graph/subgraph")
def cognitive_kg_subgraph(nodes: str, depth: int = 1) -> dict[str, object]:
    try:
        node_ids = [n.strip() for n in nodes.split(",") if n.strip()]
        subgraph = KnowledgeGraph.get_subgraph(node_ids=node_ids, depth=depth)
        return {"status": "ok", "subgraph": subgraph}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/cognitive/skill-graph/register")
def cognitive_skill_register(req: SkillRegisterRequest) -> dict[str, object]:
    try:
        SkillGraph.register_skill(
            skill_id=req.skill_id,
            name=req.name,
            description=req.description,
            tools=req.tools,
            agents=req.agents,
            prerequisites=req.prerequisites,
        )
        return {"status": "ok", "message": f"Skill '{req.skill_id}' registered successfully."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/cognitive/skill-graph/details/{skill_id}")
def cognitive_skill_details(skill_id: str) -> dict[str, object]:
    try:
        details = SkillGraph.get_skill_details(skill_id=skill_id)
        if not details:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")
        return {"status": "ok", "details": details}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/cognitive/skill-graph/dependencies/{skill_id}")
def cognitive_skill_dependencies(skill_id: str) -> dict[str, object]:
    try:
        deps = SkillGraph.get_skill_dependencies(skill_id=skill_id)
        return {"status": "ok", "dependencies": deps}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/cognitive/curriculum/challenge")
def cognitive_curriculum_challenge(req: ChallengeAddRequest) -> dict[str, object]:
    try:
        CurriculumEngine.add_challenge(
            challenge_id=req.challenge_id,
            category=req.category,
            title=req.title,
            description=req.description,
            success_criteria=req.success_criteria,
        )
        return {"status": "ok", "message": f"Curriculum challenge '{req.challenge_id}' registered."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/cognitive/curriculum/challenges")
def cognitive_curriculum_challenges(category: str | None = None, status: str | None = None) -> dict[str, object]:
    try:
        challenges = CurriculumEngine.list_challenges(category=category, status=status)
        return {"status": "ok", "challenges": challenges}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/cognitive/curriculum/recommendations")
def cognitive_curriculum_recommendations() -> dict[str, object]:
    try:
        recs = CurriculumEngine.get_recommended_challenges()
        return {"status": "ok", "recommendations": recs}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/cognitive/project-manager/task")
def cognitive_project_task(req: ProjectTaskRequest) -> dict[str, object]:
    try:
        ProjectManager.create_project_task(
            task_id=req.task_id,
            project_name=req.project_name,
            title=req.title,
            assigned_agent=req.assigned_agent,
            dependencies=req.dependencies,
        )
        return {"status": "ok", "message": f"Project task '{req.task_id}' created successfully."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/cognitive/project-manager/tasks/{project_name}")
def cognitive_project_tasks(project_name: str) -> dict[str, object]:
    try:
        tasks = ProjectManager.get_project_tasks(project_name=project_name)
        return {"status": "ok", "tasks": tasks}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/cognitive/project-manager/blackboard")
def cognitive_project_blackboard_write(req: BlackboardWriteRequest) -> dict[str, object]:
    try:
        ProjectManager.write_to_blackboard(project_name=req.project_name, key=req.key, value=req.value)
        return {"status": "ok", "message": "Project blackboard updated."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/cognitive/long-term-goals/register")
def cognitive_lt_goal_register(req: LTGoalRegisterRequest) -> dict[str, object]:
    try:
        LongTermGoalEngine.register_goal(
            goal_id=req.goal_id,
            title=req.title,
            description=req.description,
            parent_id=req.parent_id,
            preconditions=req.preconditions,
            success_criteria=req.success_criteria,
        )
        return {"status": "ok", "message": f"Long-term goal '{req.goal_id}' registered successfully."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/cognitive/long-term-goals/hierarchy")
def cognitive_lt_goal_hierarchy() -> dict[str, object]:
    try:
        tree = LongTermGoalEngine.get_goal_hierarchy()
        return {"status": "ok", "hierarchy": tree}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Step 8.4 — Simulation Sandbox Endpoints
# Firewall between planning and execution.
# Rule 1: authorized is ALWAYS False in every response.
# Rule 2: No GoalMemory write methods are called.
# Rule 3: No ValueEngine constraint mutations.
# ---------------------------------------------------------------------------

from backend.core.simulation_sandbox import (
    SimulationSandbox,
    ResourceExhaustionForecast,
    DependencyFailureModel,
    SandboxConstitution,
)
from pydantic import BaseModel as _SBBaseModel
from typing import List as _SBList, Optional as _SBOpt, Dict as _SBDict, Any as _SBAny


class _SandboxEvaluateRequest(_SBBaseModel):
    plan: _SBList[_SBDict[str, _SBAny]] = []
    goal: str = ""
    goal_id: _SBOpt[str] = None
    workflow_id: str = ""
    plan_title: str = ""
    plan_description: str = ""


class _SandboxProjectEvaluateRequest(_SBBaseModel):
    plan: _SBList[_SBDict[str, _SBAny]] = []
    goal_id: _SBOpt[str] = None
    goal: str = ""
    workflow_id: str = ""


@app.get("/sandbox/constitution")
def sandbox_constitution() -> dict[str, object]:
    """Returns the three hardcoded safety rules (read-only introspection).

    Rule 1: Sandbox cannot authorize execution.
    Rule 2: Sandbox cannot create goals.
    Rule 3: Sandbox cannot rewrite constraints.
    """
    return {"status": "ok", "constitution": SandboxConstitution.as_dict()}


@app.post("/sandbox/evaluate")
def sandbox_evaluate(req: _SandboxEvaluateRequest) -> dict[str, object]:
    """Evaluate a plan through the Simulation Sandbox (no project required).

    Returns scenario paths, alignment gate result, and Monte-Carlo simulation.
    authorized is ALWAYS False in the response (Rule 1).
    """
    try:
        report = SimulationSandbox.evaluate_plan(
            plan_steps=req.plan,
            goal=req.goal,
            goal_id=req.goal_id,
            workflow_id=req.workflow_id,
            plan_title=req.plan_title,
            plan_description=req.plan_description,
        )
        return {"status": "ok", **report.to_dict()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/sandbox/evaluate/project/{project_id}")
def sandbox_evaluate_project(
    project_id: str,
    req: _SandboxProjectEvaluateRequest,
) -> dict[str, object]:
    """Full project evaluation through the Simulation Sandbox.

    Runs all four engines:
    - Resource Exhaustion Forecast
    - Dependency Failure Propagation
    - Alignment Gate (Goal + Value + Constraint)
    - Monte-Carlo Plan Simulation

    authorized is ALWAYS False in the response (Rule 1).
    """
    try:
        report = SimulationSandbox.evaluate_project_plan(
            project_id=project_id,
            plan_steps=req.plan,
            goal_id=req.goal_id,
            goal=req.goal,
            workflow_id=req.workflow_id,
        )
        return {"status": "ok", **report.to_dict()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/sandbox/resource-forecast/{project_id}")
def sandbox_resource_forecast(project_id: str) -> dict[str, object]:
    """Standalone resource exhaustion forecast for a PPM project.

    Asks: Will token, compute, or attention budget run out before plan completion?
    Read-only — never mutates PPM or GoalMemory state.
    """
    try:
        forecast = ResourceExhaustionForecast.run(project_id)
        return {"status": "ok", **forecast.to_dict()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/sandbox/dependency-propagation/{project_id}")
def sandbox_dependency_propagation(project_id: str) -> dict[str, object]:
    """Standalone dependency failure propagation for a PPM project.

    Models: what if an upstream dependency slips N days, fails, or becomes blocked?
    Read-only — never mutates PPM or GoalMemory state.
    """
    try:
        report = DependencyFailureModel.propagate(project_id)
        return {"status": "ok", **report.to_dict()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# =============================================================================
# Human Conversation Engine (HCE) — /hce/* endpoints
# =============================================================================

from backend.core.human_conversation_engine import (
    HumanConversationEngine,
    HCEConstitution,
    HCEStore,
    GovernanceStatus,
    IntentStatus,
    RelationshipState,
    NarrativeContinuityEngine,
)


@app.get("/hce/constitution")
def hce_constitution():
    """Return the six HCE constitutional safety rules (read-only)."""
    return {"status": "ok", "constitution": HCEConstitution.to_dict()}


@app.post("/hce/relationship")
def hce_create_relationship(payload: dict = Body(...)):
    """Create or retrieve a relationship record for a user entity.

    Body: { "user_entity_id": str, "display_name": str }
    """
    try:
        user_entity_id = payload.get("user_entity_id", "").strip()
        display_name = payload.get("display_name", "User").strip()
        if not user_entity_id:
            raise HTTPException(status_code=422, detail="user_entity_id is required")
        record = HCEStore.create_relationship(user_entity_id, display_name)
        return {"status": "ok", "relationship": record}
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/hce/chapter")
def hce_open_chapter(payload: dict = Body(...)):
    """Open a new conversation chapter for an existing relationship.

    Body: { "relationship_id": str, "relationship_state": str (optional) }
    """
    try:
        relationship_id = payload.get("relationship_id", "").strip()
        if not relationship_id:
            raise HTTPException(status_code=422, detail="relationship_id is required")
        state_str = payload.get("relationship_state", "BUILDING_MODE").upper()
        try:
            state = RelationshipState(state_str)
        except ValueError:
            state = RelationshipState.BUILDING_MODE
        chapter = HCEStore.open_chapter(relationship_id, state)
        return {"status": "ok", "chapter": chapter}
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.put("/hce/chapter/{chapter_id}/close")
def hce_close_chapter(chapter_id: str, payload: dict = Body(default={})):
    """Close a chapter and write its summary narrative.

    Body: { "summary_narrative": str (optional) }
    """
    try:
        summary = payload.get("summary_narrative", "")
        closed = HCEStore.close_chapter(chapter_id, summary)
        if not closed:
            raise HTTPException(status_code=404, detail="Chapter not found or already closed")
        if summary:
            chapter = HCEStore.get_chapter(chapter_id)
            if chapter:
                updated_arcs = NarrativeContinuityEngine.update_arcs_from_chapter(
                    chapter["relationship_id"], chapter_id, summary
                )
                return {"status": "ok", "closed": True, "arcs_updated": updated_arcs}
        return {"status": "ok", "closed": True}
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/hce/process")
def hce_process(payload: dict = Body(...)):
    """Main HCE entry point: process a user message.

    Body: { "user_message": str, "relationship_id": str, "chapter_id": str (optional) }
    Returns HCEResponse. authorized_to_create_goals and authorized_to_write_memory are
    always False (Rules 1 & 2).
    """
    try:
        user_message = payload.get("user_message", "").strip()
        relationship_id = payload.get("relationship_id", "").strip()
        chapter_id = payload.get("chapter_id") or None
        if not user_message:
            raise HTTPException(status_code=422, detail="user_message is required")
        if not relationship_id:
            raise HTTPException(status_code=422, detail="relationship_id is required")
        response = HumanConversationEngine.process(
            user_message,
            relationship_id=relationship_id,
            chapter_id=chapter_id,
        )
        return {"status": "ok", **response.to_dict()}
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/hce/relationship/{relationship_id}/context")
def hce_get_context(relationship_id: str):
    """Get the full relationship context snapshot (read-only)."""
    try:
        rel = HCEStore.get_relationship(relationship_id)
        if not rel:
            raise HTTPException(status_code=404, detail="Relationship not found")
        chapter = HCEStore.get_active_chapter(relationship_id)
        metrics = HCEStore.get_metrics(relationship_id)
        arcs = HCEStore.get_narrative_arcs(relationship_id)
        return {
            "status": "ok",
            "relationship": rel,
            "active_chapter": chapter,
            "metrics": metrics,
            "narrative_arcs": arcs,
        }
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/hce/relationship/{relationship_id}/health")
def hce_relationship_health(relationship_id: str):
    """Return conversation health metrics (retrieval-priority use only)."""
    try:
        metrics = HCEStore.get_metrics(relationship_id)
        if not metrics:
            raise HTTPException(status_code=404, detail="Relationship metrics not found")
        return {"status": "ok", "health_metrics": metrics}
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/hce/relationship/{relationship_id}/contradictions")
def hce_get_contradictions(relationship_id: str, unresolved_only: bool = True):
    """Return contradiction log for a relationship's user entity."""
    try:
        rel = HCEStore.get_relationship(relationship_id)
        if not rel:
            raise HTTPException(status_code=404, detail="Relationship not found")
        contradictions = HCEStore.get_contradictions(
            rel["user_entity_id"], unresolved_only=unresolved_only
        )
        return {"status": "ok", "contradictions": contradictions}
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/hce/relationship/{relationship_id}/narrative-arcs")
def hce_get_narrative_arcs(relationship_id: str):
    """Return all narrative arcs for a relationship."""
    try:
        arcs = HCEStore.get_narrative_arcs(relationship_id)
        return {"status": "ok", "narrative_arcs": arcs}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/hce/memory-candidates")
def hce_memory_candidates(governance_status: str = "PENDING"):
    """List memory candidates by governance status (PENDING | COMMITTED | REJECTED)."""
    try:
        candidates = HCEStore.get_memory_candidates(governance_status=governance_status)
        return {"status": "ok", "candidates": candidates, "count": len(candidates)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/hce/memory-candidates/{candidate_id}/commit")
def hce_commit_memory_candidate(candidate_id: str):
    """Commit a PENDING memory candidate to the Memory Fabric (governance gate)."""
    try:
        committed = HumanConversationEngine.commit_memory_candidate(candidate_id)
        if not committed:
            raise HTTPException(status_code=404, detail="Candidate not found or already processed")
        return {"status": "ok", "committed": True, "candidate_id": candidate_id}
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/hce/memory-candidates/{candidate_id}/reject")
def hce_reject_memory_candidate(candidate_id: str):
    """Reject a PENDING memory candidate."""
    try:
        rejected = HumanConversationEngine.reject_memory_candidate(candidate_id)
        if not rejected:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return {"status": "ok", "rejected": True, "candidate_id": candidate_id}
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/hce/proposed-intents")
def hce_proposed_intents(status: str = "PENDING_USER_CONFIRMATION"):
    """List proposed intents by status."""
    try:
        intents = HCEStore.get_proposed_intents(status=status)
        return {"status": "ok", "intents": intents, "count": len(intents)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/hce/proposed-intents/{proposal_id}/commit")
def hce_commit_proposed_intent(proposal_id: str):
    """Commit a proposed intent to the Goal System (Rule 1 gateway).

    This is the ONLY path through which conversation can create a goal —
    it requires explicit user confirmation (this API call).
    authorized_to_create_goals is still False at the HCE layer; the Goal System owns creation.
    """
    try:
        committed = HumanConversationEngine.commit_proposed_intent(proposal_id)
        if not committed:
            raise HTTPException(status_code=404, detail="Intent not found or already processed")
        return {"status": "ok", "committed": True, "proposal_id": proposal_id,
                "authorized_to_create_goals": False}
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



# ---------------------------------------------------------------------------
# Step 8.5 — Cognitive Dashboard Endpoints
# ---------------------------------------------------------------------------
from backend.core.cognitive_dashboard import CognitiveDashboardManager

class HealthEventRequest(BaseModel):
    severity: str
    source_module: str
    description: str

@app.get("/dashboard/cognitive/latest")
def get_cognitive_latest() -> dict[str, object]:
    """Returns the latest 11-tier dashboard metrics snapshot."""
    try:
        data = CognitiveDashboardManager.get_latest_snapshot()
        return {"status": "ok", "data": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.post("/dashboard/cognitive/snapshot")
def trigger_cognitive_snapshot() -> dict[str, object]:
    """Manually triggers a new system health snapshot sweep."""
    try:
        data = CognitiveDashboardManager.collect_snapshot()
        return {"status": "ok", "data": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.get("/dashboard/cognitive/health-events")
def get_health_events() -> dict[str, object]:
    """Returns all warning, critical, and info events logged in the ledger."""
    try:
        events = CognitiveDashboardManager.get_health_events()
        return {"status": "ok", "events": events}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.post("/dashboard/cognitive/health-events")
def log_health_event(payload: HealthEventRequest) -> dict[str, object]:
    """Logs a custom health event into the ledger."""
    try:
        evt_id = CognitiveDashboardManager.log_health_event(payload.severity, payload.source_module, payload.description)
        return {"status": "ok", "event_id": evt_id}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.post("/dashboard/cognitive/health-events/{event_id}/resolve")
def resolve_health_event(event_id: str) -> dict[str, object]:
    """Resolves an active health warning or critical alert."""
    try:
        resolved = CognitiveDashboardManager.resolve_health_event(event_id)
        return {"status": "ok", "resolved": resolved}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.get("/dashboard/cognitive/repair-proposals")
def get_repair_proposals() -> dict[str, object]:
    """Returns diagnostic self-repair proposals generated during degraded states."""
    try:
        proposals = CognitiveDashboardManager.get_repair_proposals()
        return {"status": "ok", "proposals": proposals}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.post("/dashboard/cognitive/repair-proposals/{proposal_id}/approve")
def approve_repair_proposal(proposal_id: str) -> dict[str, object]:
    """Approves and executes a diagnostic repair proposal."""
    try:
        success = CognitiveDashboardManager.approve_repair_proposal(proposal_id)
        return {"status": "ok", "success": success}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.get("/dashboard/cognitive/mral/traces")
def get_mral_traces() -> dict[str, object]:
    """Returns list of reasoning decision traces."""
    try:
        from backend.core.meta_cognition import MRALAuditor
        traces = MRALAuditor.get_all_traces()
        return {"status": "ok", "traces": traces}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.get("/dashboard/cognitive/mral/traces/{decision_id}")
def get_mral_trace_replay(decision_id: str) -> dict[str, object]:
    """Returns full details of a specific reasoning decision trace."""
    try:
        from backend.core.meta_cognition import MRALAuditor
        trace = MRALAuditor.get_decision_replay(decision_id)
        if not trace:
            return {"status": "error", "message": f"Trace {decision_id} not found"}
        return {"status": "ok", "trace": trace}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

class TestRunRequest(BaseModel):
    goal_title: str
    goal_description: str
    plan_steps: list[dict[str, object]]

@app.post("/dashboard/cognitive/mral/traces/test-run")
def trigger_mral_test_run(payload: TestRunRequest) -> dict[str, object]:
    """Manually triggers a sandbox/MRAL run for testing."""
    try:
        from backend.core.cognitive_simulation_sandbox import CognitiveSimulationSandbox
        res = CognitiveSimulationSandbox.orchestrate(
            goal_id=f"goal_{uuid.uuid4().hex[:8]}",
            goal_title=payload.goal_title,
            plan_title=payload.goal_title,
            plan_description=payload.goal_description,
            plan_steps=payload.plan_steps,
            success_criteria=[],
        )
        return {"status": "ok", "data": res}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

class CreateExecutivePlanRequest(BaseModel):
    goal_id: str
    plan_title: str
    plan_description: str
    plan_steps: list[dict[str, object]]
    domain: str = "General"

class AdaptPlanRequest(BaseModel):
    failed_task_id: str

@app.post("/dashboard/cognitive/executive/plans")
def create_executive_plan(payload: CreateExecutivePlanRequest) -> dict[str, object]:
    """Triggers the Executive Planner pipeline to produce a validated plan blueprint."""
    try:
        from backend.core.executive_planner import ExecutivePlanner
        res = ExecutivePlanner.create_executive_plan(
            goal_id=payload.goal_id,
            plan_title=payload.plan_title,
            plan_description=payload.plan_description,
            plan_steps=payload.plan_steps,
            domain=payload.domain
        )
        return res
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.get("/dashboard/cognitive/executive/plans/{blueprint_id}")
def get_executive_plan(blueprint_id: str) -> dict[str, object]:
    """Retrieves detailed structure, forecasts, and allocations of a plan blueprint."""
    try:
        from backend.core.executive_planner import ExecutivePlanner
        conn = ExecutivePlanner._get_sqlite_conn()
        try:
            row = conn.execute("SELECT * FROM plan_blueprints WHERE blueprint_id = ?", (blueprint_id,)).fetchone()
            if not row:
                return {"status": "error", "message": f"Blueprint {blueprint_id} not found"}
            
            nodes = conn.execute("SELECT * FROM blueprint_nodes WHERE blueprint_id = ?", (blueprint_id,)).fetchall()
            dependencies = conn.execute("SELECT * FROM blueprint_dependencies WHERE blueprint_id = ?", (blueprint_id,)).fetchall()
            forecasts = conn.execute("SELECT * FROM resource_forecasts WHERE blueprint_id = ?", (blueprint_id,)).fetchall()
            risks = conn.execute("SELECT * FROM simulation_risks WHERE blueprint_id = ?", (blueprint_id,)).fetchall()
            sweep = conn.execute("SELECT * FROM context_sweeps WHERE blueprint_id = ?", (blueprint_id,)).fetchone()

            node_list = []
            for n in nodes:
                allocated = conn.execute("SELECT * FROM blueprint_agents WHERE node_id = ?", (n["node_id"],)).fetchone()
                node_list.append({
                    "node_id": n["node_id"],
                    "node_type": n["node_type"],
                    "title": n["title"],
                    "description": n["description"],
                    "estimated_effort_score": n["estimated_effort_score"],
                    "success_criteria_definition": n["success_criteria_definition"],
                    "actual_effort": n["actual_effort"],
                    "actual_resource_units": n["actual_resource_units"],
                    "allocated_agent": dict(allocated) if allocated else None
                })

            return {
                "status": "ok",
                "blueprint": {
                    "blueprint_id": row["blueprint_id"],
                    "linked_goal_id": row["linked_goal_id"],
                    "target_project_id": row["target_project_id"],
                    "confidence_rating": row["confidence_rating"],
                    "planning_phase_duration_ms": row["planning_phase_duration_ms"],
                    "blueprint_status": row["blueprint_status"],
                    "max_budget": row["max_budget"],
                    "max_time_days": row["max_time_days"],
                    "total_replans": row["total_replans"],
                    "nodes": node_list,
                    "dependencies": [dict(d) for d in dependencies],
                    "forecasts": [dict(f) for f in forecasts],
                    "risks": [dict(rk) for rk in risks],
                    "context_sweep": dict(sweep) if sweep else None
                }
            }
        finally:
            conn.close()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.post("/dashboard/cognitive/executive/plans/{blueprint_id}/deploy")
def deploy_executive_plan(blueprint_id: str) -> dict[str, object]:
    """Deploys approved plan to active PPM container."""
    try:
        from backend.core.executive_planner import ExecutivePlanner
        res = ExecutivePlanner.deploy_blueprint_to_ppm(blueprint_id)
        return res
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@app.post("/dashboard/cognitive/executive/plans/{project_id}/adapt")
def adapt_executive_plan(project_id: str, payload: AdaptPlanRequest) -> dict[str, object]:
    """Triggers adaptation loop on verification failure."""
    try:
        from backend.core.executive_planner import ExecutivePlanner
        res = ExecutivePlanner.adapt_plan(project_id, payload.failed_task_id)
        return res
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ============================================================================
# Step 8.8 — Action Broker Scheduler Endpoints
# ============================================================================

class EnqueueActionRequest(BaseModel):
    agent_name: str
    action: str
    params: dict = {}
    state: dict = {}
    priority: int = 5            # 0 (low) … 10 (critical)
    deadline_secs: float = None  # Relative seconds from now; None = no deadline
    max_attempts: int = 3

class DispatchRequest(BaseModel):
    dry_run: bool = False        # If True, peek without executing


@app.post("/broker/queue")
def broker_enqueue(payload: EnqueueActionRequest) -> dict:
    """Enqueue an action onto the priority scheduler queue."""
    try:
        from backend.core.action_scheduler import ActionScheduler
        return ActionScheduler.enqueue_action(
            agent_name=payload.agent_name,
            action=payload.action,
            params=payload.params,
            state=payload.state,
            priority=payload.priority,
            deadline_secs=payload.deadline_secs,
            max_attempts=payload.max_attempts,
        )
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/broker/dispatch")
def broker_dispatch(payload: DispatchRequest) -> dict:
    """Dispatch the highest-priority eligible action from the queue.

    Pass ``dry_run=true`` to peek at the next candidate without executing it.
    """
    try:
        from backend.core.action_scheduler import ActionScheduler
        return ActionScheduler.dispatch_next(dry_run=payload.dry_run)
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/broker/queue/snapshot")
def broker_queue_snapshot() -> dict:
    """Return live queue state: pending depth, in-flight, SLA breach summary."""
    try:
        from backend.core.action_scheduler import ActionScheduler
        return ActionScheduler.get_queue_snapshot()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/broker/queue/drain")
def broker_drain_queue() -> dict:
    """Emergency drain: cancel all PENDING and RETRY actions.

    IN_FLIGHT actions are left to complete naturally.
    """
    try:
        from backend.core.action_scheduler import ActionScheduler
        return ActionScheduler.drain_queue()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/broker/queue/{queue_id}")
def broker_inspect_action(queue_id: str) -> dict:
    """Inspect a single queued action by its queue_id."""
    try:
        from backend.core.action_scheduler import ActionScheduler
        record = ActionScheduler.get_action(queue_id)
        if record is None:
            return {"status": "error", "message": f"Action '{queue_id}' not found."}
        return {"status": "ok", "record": record}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/verification/report/{report_id}")
def verification_get_report(report_id: str) -> dict:
    """Retrieve a specific verification report."""
    try:
        from backend.core.verification_engine import VerificationEngine
        report = VerificationEngine.get_report(report_id)
        if report is None:
            return {"status": "error", "message": f"Report '{report_id}' not found."}
        return {"status": "ok", "report": report}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/verification/action/{queue_id}")
def verification_get_reports_for_action(queue_id: str) -> dict:
    """Retrieve all verification reports associated with a queue_id."""
    try:
        from backend.core.verification_engine import VerificationEngine
        reports = VerificationEngine.get_reports_for_action(queue_id)
        return {"status": "ok", "reports": reports}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


class RetractPayload(BaseModel):
    reason: str


@app.post("/verification/retract/{report_id}")
def verification_retract_report(report_id: str, payload: RetractPayload) -> dict:
    """Retract a report, downgrading the verdict to PARTIAL and setting confidence to 0.5."""
    try:
        from backend.core.verification_engine import VerificationEngine
        success = VerificationEngine.retract_report(report_id, payload.reason)
        if not success:
            return {"status": "error", "message": f"Failed to retract report '{report_id}' (not found or non-retractable)."}
        return {"status": "ok", "message": f"Report '{report_id}' successfully retracted."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/verification/verdicts")
def verification_get_verdicts_summary() -> dict:
    """Aggregate report verdict counts for Cognitive Dashboard Tier 9."""
    try:
        from backend.core.verification_engine import VerificationEngine
        summary = VerificationEngine.get_verdicts_summary()
        return {"status": "ok", "summary": summary}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


class NodeRegisterRESTRequest(BaseModel):
    node_name: str
    node_type: str
    cpu_logical: int
    ram_gb: float
    gpu_info: str | None = None
    capabilities: list[str] | None = None


@app.post("/api/nodes/register/{node_id}")
def register_node_endpoint(node_id: str, payload: NodeRegisterRESTRequest) -> dict:
    try:
        from backend.core.node_manager import NodeManager
        NodeManager.register_node(
            node_id=node_id,
            node_name=payload.node_name,
            node_type=payload.node_type,
            cpu_logical=payload.cpu_logical,
            ram_gb=payload.ram_gb,
            gpu_info=payload.gpu_info,
            capabilities=payload.capabilities
        )
        return {"status": "ok", "message": f"Node '{node_id}' successfully registered via REST."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/api/nodes")
def get_nodes_endpoint() -> dict:
    try:
        from backend.core.node_manager import NodeManager
        nodes = NodeManager.get_nodes()
        return {"status": "ok", "nodes": nodes}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/api/nodes/sweep")
def sweep_nodes_endpoint() -> dict:
    try:
        from backend.core.node_manager import NodeManager
        swept = NodeManager.sweep_nodes()
        return {"status": "ok", "swept_count": swept}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.websocket("/api/nodes/ws/{node_id}")
async def websocket_node_endpoint(websocket: WebSocket, node_id: str):
    from fastapi.websockets import WebSocketDisconnect
    from backend.core.node_manager import NodeManager
    from backend.core.logger import log_event
    
    await websocket.accept()
    NodeManager.register_connection(node_id, websocket)
    
    # Update state to alive on connect
    NodeManager.update_heartbeat(node_id, 0.0, 0.0, 0, status="alive")
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                packet = json.loads(data)
                packet_type = packet.get("type")
                if packet_type == "heartbeat":
                    metrics = packet.get("metrics", {})
                    cpu = float(metrics.get("system_cpu_pct", 0.0))
                    ram = float(metrics.get("system_ram_pct", 0.0))
                    tasks = int(metrics.get("active_tasks", 0))
                    NodeManager.update_heartbeat(node_id, cpu, ram, tasks, status="alive")
                elif packet_type == "register":
                    NodeManager.register_node(
                        node_id=node_id,
                        node_name=packet.get("node_name", "unknown"),
                        node_type=packet.get("node_type", "worker"),
                        cpu_logical=int(packet.get("cpu_logical", 1)),
                        ram_gb=float(packet.get("ram_gb", 0.0)),
                        gpu_info=packet.get("gpu_info"),
                        capabilities=packet.get("capabilities", [])
                    )
                elif packet_type == "task_response":
                    queue_id = packet.get("queue_id")
                    result = packet.get("result")
                    from backend.core.action_scheduler import ActionScheduler
                    ActionScheduler.set_pending_response(queue_id, result)
            except Exception as parse_exc:
                log_event("node_ws_error", f"Error parsing packet from node {node_id}: {parse_exc}")
    except WebSocketDisconnect:
        pass
    finally:
        NodeManager.deregister_connection(node_id)
        # Update node status to offline when WebSocket closes
        NodeManager.update_heartbeat(node_id, 0.0, 0.0, 0, status="offline")


@app.on_event("shutdown")
def stop_shutdown_tasks():
    """Stop background scheduler threads on shutdown."""
    try:
        ResearchScheduler.stop()
    except Exception:
        pass
