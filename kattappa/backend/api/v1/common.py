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








class BenchmarkVariantGenerateRequest(BaseModel):
    suite_id: str
    input_text: str
    expected_answer: str
    n: int = 5
    seed_int: int | None = None


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


import threading

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



class MimoCodeRequest(BaseModel):
    prompt: str
    file_path: str


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


def _action_records_payload(records: list[Any]) -> list[dict[str, object]]:
    return [record.to_dict() for record in records]


class JarvisSettingsRequest(BaseModel):
    enabled: bool


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


from backend.core.learning_dashboard import LearningDashboard  # noqa: E402


from backend.core.burn_in_governance import BurnInGovernance, ResearchDebtLedger, PredictionReliabilityTracker  # noqa: E402


from backend.core.research_scheduler import ResearchScheduler  # noqa: E402


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


from backend.core.human_conversation_engine import (
    HumanConversationEngine,
    HCEConstitution,
    HCEStore,
    GovernanceStatus,
    IntentStatus,
    RelationshipState,
    NarrativeContinuityEngine,
)


from backend.core.cognitive_dashboard import CognitiveDashboardManager

class HealthEventRequest(BaseModel):
    severity: str
    source_module: str
    description: str

class TestRunRequest(BaseModel):
    goal_title: str
    goal_description: str
    plan_steps: list[dict[str, object]]

class CreateExecutivePlanRequest(BaseModel):
    goal_id: str
    plan_title: str
    plan_description: str
    plan_steps: list[dict[str, object]]
    domain: str = "General"

class AdaptPlanRequest(BaseModel):
    failed_task_id: str

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


class RetractPayload(BaseModel):
    reason: str


class NodeRegisterRESTRequest(BaseModel):
    node_name: str
    node_type: str
    cpu_logical: int
    ram_gb: float
    gpu_info: str | None = None
    capabilities: list[str] | None = None


def stop_shutdown_tasks():
    """Stop background scheduler threads on shutdown."""
    try:
        ResearchScheduler.stop()
    except Exception:
        pass


__all__ = [name for name in globals() if not name.startswith('__')]
