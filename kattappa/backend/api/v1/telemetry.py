import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, List

from backend.core.ledger.telemetry.metrics_collector import MetricsCollector
from backend.core.ledger.telemetry.telemetry_service import TelemetryService
from backend.core.cos.kernel import KERNEL
from backend.core.observability.telemetry import TelemetryCollector
from backend.core.observability.visualizer import TraceVisualizer
from backend.core.observability.planner_analytics import PlannerAnalytics
from backend.core.observability.diagnostics import export_diagnostics_bundle
from backend.core.observability.provenance_logger import log_decision
from backend.core.observability.calibration_cal import compile_calibration_report
from backend.core.governance.delegation_token_manager import mint_delegation_token
from backend.core.governance.skill_dependency_graph import verify_dependencies
from backend.core.governance.skill_resolver import resolve_skill_by_intent
from backend.core.governance.sandbox_allocator import allocate_sandbox_and_run
from backend.core.governance.permission_governor import PermissionGovernor
from backend.core.governance.policy_engine import PolicyEngine
from backend.core.governance.safety_monitor import SafetyMonitor
from backend.core.governance.goal_lifecycle import GoalLifecycleGovernor, GoalStatus, GoalTransitionError
from backend.core.governance.goal_scheduler import GoalPriorityScheduler

telemetry_router = APIRouter(tags=["Telemetry"])

GLOBAL_COLLECTOR = MetricsCollector()
GLOBAL_TELEMETRY = TelemetryService(GLOBAL_COLLECTOR)
GLOBAL_SCHEDULER = GoalPriorityScheduler()


class RecordMetricRequest(BaseModel):
    metric_name: str
    value: float


class RecordDecisionRequest(BaseModel):
    stage: str
    action: str
    reason: str
    alternatives: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RecordOutcomeRequest(BaseModel):
    decision_id: str
    trace_id: str
    stage: str
    predicted_confidence: float
    actual_result: int
    error_message: str | None = None


class MintTokenRequest(BaseModel):
    trace_id: str
    capabilities: List[str]
    expires_in_minutes: int = 30
    max_invocations: int = 10
    allowed_paths: List[str] = Field(default_factory=list)
    allowed_domains: List[str] = Field(default_factory=list)
    issued_by: str = "user"


class SkillManifestRequest(BaseModel):
    name: str
    version: str
    description: str | None = None
    entrypoint: str
    required_capabilities: List[str] = Field(default_factory=list)
    dependencies: List[Dict[str, str]] = Field(default_factory=list)
    sandbox_type: str = "subprocess"
    timeout_seconds: int = 30
    max_memory_mb: int | None = None
    allow_network: bool = False
    allowed_paths: List[str] = Field(default_factory=list)


class ExecuteSkillRequest(BaseModel):
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    agent_name: str = "coder"


@telemetry_router.get("/telemetry/report")
def get_telemetry_report() -> Dict[str, Any]:
    """Generates the rolling operational metrics report."""
    return GLOBAL_TELEMETRY.generate_report()


@telemetry_router.get("/telemetry/traces")
def get_request_traces() -> Dict[str, Any]:
    """Retrieves all collected and finalized request traces."""
    from backend.core.governance.request_tracer import GLOBAL_TRACES, TRACES_LOCK
    with TRACES_LOCK:
        # Return in reverse chronological order (newest first)
        return {"traces": list(reversed(GLOBAL_TRACES))}



@telemetry_router.post("/telemetry/record")
def record_metric(request: RecordMetricRequest) -> Dict[str, Any]:
    """Records a live operational metric."""
    GLOBAL_COLLECTOR.record(request.metric_name, request.value)
    return {"status": "success", "metric": request.metric_name, "value": request.value}


@telemetry_router.get("/telemetry/timeline", response_class=PlainTextResponse)
def get_telemetry_timeline() -> str:
    """Returns the visual execution trace timeline as text tree."""
    collector = TelemetryCollector()
    return TraceVisualizer.format_tree(collector.get_spans())


@telemetry_router.get("/telemetry/stats")
def get_telemetry_stats() -> Dict[str, Any]:
    """Returns aggregated performance and tool statistics compiled from trace spans."""
    collector = TelemetryCollector()
    return PlannerAnalytics.compile(collector.get_spans())


@telemetry_router.get("/telemetry/diagnostics")
def get_telemetry_diagnostics() -> FileResponse:
    """Exports and serves a zipped diagnostics package containing logs and system stats."""
    try:
        zip_path = export_diagnostics_bundle()
        return FileResponse(
            path=str(zip_path),
            filename=zip_path.name,
            media_type="application/zip",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate diagnostics bundle: {e}")


@telemetry_router.post("/telemetry/decision")
def post_decision(request: RecordDecisionRequest) -> Dict[str, Any]:
    """Records a cognitive decision event manually."""
    decision_id = log_decision(
        stage=request.stage,
        action=request.action,
        reason=request.reason,
        alternatives=request.alternatives,
        confidence=request.confidence,
        inputs=request.inputs,
        outputs=request.outputs,
        metadata=request.metadata,
    )
    return {"status": "success", "decision_id": decision_id}


@telemetry_router.get("/telemetry/provenance/{trace_id}")
def get_trace_provenance(trace_id: str) -> Dict[str, Any]:
    """Retrieves all reasoning decisions and trace spans matching the target trace ID."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    
    # Query decisions matching the trace ID
    decisions = KERNEL.ledger.get_decisions(trace_id)
    
    # Return decisions and trace matching metrics
    return {
        "status": "success",
        "trace_id": trace_id,
        "decisions": decisions,
    }


@telemetry_router.get("/telemetry/provenance/decisions/{stage}")
def get_stage_decisions(stage: str) -> List[Dict[str, Any]]:
    """Retrieves recent decisions associated with the target cognitive stage."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    return KERNEL.ledger.get_decisions_by_stage(stage)


@telemetry_router.get("/telemetry/events")
def get_ledger_events() -> List[Dict[str, Any]]:
    """Retrieves all events stored in the global execution ledger."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    events = KERNEL.ledger.query({})
    return [e.to_dict() for e in events]


@telemetry_router.get("/telemetry/events/{event_id}/ancestors")
def get_event_ancestors(event_id: str) -> List[Dict[str, Any]]:
    """Retrieves all ancestors of the target event."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    events = KERNEL.ledger.ancestors(event_id)
    return [e.to_dict() for e in events]


@telemetry_router.get("/telemetry/events/{event_id}/descendants")
def get_event_descendants(event_id: str) -> List[Dict[str, Any]]:
    """Retrieves all descendants of the target event."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    events = KERNEL.ledger.descendants(event_id)
    return [e.to_dict() for e in events]


@telemetry_router.post("/telemetry/outcome")
def post_outcome(request: RecordOutcomeRequest) -> Dict[str, Any]:
    """Records the execution outcome of a decision for calibration."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    calibration_id = str(uuid.uuid4())
    KERNEL.ledger.record_outcome(
        calibration_id=calibration_id,
        decision_id=request.decision_id,
        trace_id=request.trace_id,
        stage=request.stage,
        predicted_confidence=request.predicted_confidence,
        actual_result=request.actual_result,
        error_message=request.error_message,
    )
    return {"status": "success", "calibration_id": calibration_id}


@telemetry_router.get("/telemetry/calibration/report")
def get_calibration_report(stage: str | None = None) -> Dict[str, Any]:
    """Retrieves computed calibration metrics (ECE, Brier Score, and Histograms)."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    calibrations = KERNEL.ledger.get_calibrations(stage)
    return compile_calibration_report(calibrations)


@telemetry_router.get("/telemetry/receipts/{trace_id}")
def get_receipts(trace_id: str) -> List[Dict[str, Any]]:
    """Retrieves all execution receipts matching the trace ID."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    return KERNEL.ledger.get_execution_receipts(trace_id)


@telemetry_router.post("/telemetry/delegation/token")
def post_delegation_token(request: MintTokenRequest) -> Dict[str, Any]:
    """Mints a delegation token enabling scoped capabilities override."""
    return mint_delegation_token(
        trace_id=request.trace_id,
        capabilities=request.capabilities,
        expires_in_minutes=request.expires_in_minutes,
        max_invocations=request.max_invocations,
        allowed_paths=request.allowed_paths,
        allowed_domains=request.allowed_domains,
        issued_by=request.issued_by,
    )


@telemetry_router.get("/telemetry/delegation/token/{token_id}")
def get_delegation_token_api(token_id: str) -> Dict[str, Any]:
    """Retrieves metadata and usage counts of a delegation token."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    token = KERNEL.ledger.get_delegation_token(token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found.")
    return token


@telemetry_router.post("/skills/install")
def post_install_skill(request: SkillManifestRequest) -> Dict[str, Any]:
    """Installs a skill and runs verification checks on its dependency graph."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    skill_id = f"SKL-{str(uuid.uuid4())[:8].upper()}"
    skill = {
        "skill_id": skill_id,
        "name": request.name,
        "version": request.version,
        "description": request.description,
        "entrypoint": request.entrypoint,
        "required_capabilities": request.required_capabilities,
        "dependencies": request.dependencies,
        "sandbox_type": request.sandbox_type,
        "timeout_seconds": request.timeout_seconds,
        "max_memory_mb": request.max_memory_mb,
        "allow_network": request.allow_network,
        "allowed_paths": request.allowed_paths,
    }
    
    # Temporarily register skill to verify dependency integrity
    KERNEL.ledger.register_skill(skill)
    active_skills = KERNEL.ledger.list_skills()
    ok, error_msg = verify_dependencies(request.name, active_skills)
    if not ok:
        KERNEL.ledger.remove_skill(request.name)
        raise HTTPException(status_code=400, detail=f"Dependency verification failed: {error_msg}")
        
    return {"status": "success", "skill_id": skill_id}


@telemetry_router.get("/skills/search")
def get_search_skills() -> List[Dict[str, Any]]:
    """Lists all active skills in the registry."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    return KERNEL.ledger.list_skills()


@telemetry_router.get("/skills/resolve")
def get_resolve_skill(intent: str) -> List[Dict[str, Any]]:
    """Resolves skills mapped to the user intent semantic keywords."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    active_skills = KERNEL.ledger.list_skills()
    return resolve_skill_by_intent(intent, active_skills)


@telemetry_router.post("/skills/execute")
def post_execute_skill(request: ExecuteSkillRequest) -> Dict[str, Any]:
    """Runs a skill after verifying capability permissions and safety monitor checks."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    skill = KERNEL.ledger.get_skill(request.name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{request.name}' not found.")
        
    # Verify capability permissions for each required capability of this skill
    policy = PolicyEngine(allow_network=True)
    safety = SafetyMonitor()
    for cap in skill.get("required_capabilities", []):
        ok, status = PermissionGovernor.authorize_action_request(
            agent_name=request.agent_name,
            tool_name=cap,
            args=request.args,
            policy=policy,
            safety=safety,
        )
        if not ok:
            raise HTTPException(
                status_code=403,
                detail=f"Execution blocked: required capability '{cap}' was denied: {status}",
            )
            
    # Run the skill inside the sandbox
    # Pass through sandbox configuration from the persisted skill manifest
    sandboxed_skill = dict(skill)
    sandboxed_skill.setdefault("max_memory_mb", None)
    sandboxed_skill.setdefault("allow_network", False)
    sandboxed_skill.setdefault("allowed_paths", [])
    return allocate_sandbox_and_run(sandboxed_skill, request.args)


@telemetry_router.delete("/skills/uninstall")
def delete_uninstall_skill(name: str) -> Dict[str, Any]:
    """Removes a skill from the registry."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )
    KERNEL.ledger.remove_skill(name)
    return {"status": "success"}


# ─────────────────────────────────────────────────────────────────────────────
# Goal Lifecycle Governor Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class CreateGoalRequest(BaseModel):
    title: str
    description: str | None = None
    priority: int = 5
    owner: str | None = None
    owner_id: str | None = None
    deadline_utc: float | None = None
    confidence: float = 1.0
    max_retries: int = 3
    parent_goal_id: str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GoalTransitionRequest(BaseModel):
    status: str


class AddSubgoalRequest(BaseModel):
    title: str
    description: str | None = None
    priority: int = 5
    owner: str | None = None
    owner_id: str | None = None
    deadline_utc: float | None = None
    confidence: float = 1.0
    max_retries: int = 3


class RegisterPrincipalRequest(BaseModel):
    name: str
    principal_type: str
    trust_level: int | str | None = None
    capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    principal_id: str | None = None
    public_key: str | None = None


def _require_ledger() -> None:
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        raise HTTPException(
            status_code=500,
            detail="Execution Ledger store is not registered in Cognitive Kernel.",
        )


@telemetry_router.post("/goals/create")
def post_create_goal(request: CreateGoalRequest) -> Dict[str, Any]:
    """Creates a new goal in CREATED status."""
    _require_ledger()
    governor = GoalLifecycleGovernor(KERNEL.ledger)
    try:
        goal = governor.create_goal(
            title=request.title,
            description=request.description,
            priority=request.priority,
            owner=request.owner,
            owner_id=request.owner_id,
            deadline_utc=request.deadline_utc,
            confidence=request.confidence,
            max_retries=request.max_retries,
            parent_goal_id=request.parent_goal_id,
            metadata=request.metadata,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"status": "success", "goal": goal}


@telemetry_router.get("/goals/list")
def get_list_goals(
    status: str | None = None,
    owner: str | None = None,
) -> Dict[str, Any]:
    """Lists all goals, filterable by status and owner."""
    _require_ledger()
    goals = KERNEL.ledger.list_goals(status=status, owner=owner)
    return {"goals": goals, "count": len(goals)}


@telemetry_router.get("/goals/ready")
def get_ready_goals() -> Dict[str, Any]:
    """Returns the priority-ranked list of READY goals."""
    _require_ledger()
    ready = KERNEL.ledger.list_goals(status=GoalStatus.READY.value)
    ranked = GLOBAL_SCHEDULER.rank_ready_goals(ready)
    return {"goals": ranked, "count": len(ranked)}


@telemetry_router.get("/goals/{goal_id}")
def get_goal(goal_id: str) -> Dict[str, Any]:
    """Returns full goal detail including subgoals."""
    _require_ledger()
    goal = KERNEL.ledger.get_goal(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail=f"Goal '{goal_id}' not found.")
    subgoals = KERNEL.ledger.list_subgoals(goal_id)
    return {"goal": goal, "subgoals": subgoals}


@telemetry_router.post("/goals/{goal_id}/transition")
def post_transition_goal(goal_id: str, request: GoalTransitionRequest) -> Dict[str, Any]:
    """Transitions a goal to a new status."""
    _require_ledger()
    governor = GoalLifecycleGovernor(KERNEL.ledger)
    try:
        updated = governor.transition(goal_id, request.status)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except GoalTransitionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "success", "goal": updated}


@telemetry_router.post("/goals/{goal_id}/subgoal")
def post_add_subgoal(goal_id: str, request: AddSubgoalRequest) -> Dict[str, Any]:
    """Adds a child subgoal under the specified parent goal."""
    _require_ledger()
    parent = KERNEL.ledger.get_goal(goal_id)
    if parent is None:
        raise HTTPException(status_code=404, detail=f"Parent goal '{goal_id}' not found.")
    governor = GoalLifecycleGovernor(KERNEL.ledger)
    try:
        subgoal = governor.create_goal(
            title=request.title,
            description=request.description,
            priority=request.priority,
            owner=request.owner,
            owner_id=request.owner_id,
            deadline_utc=request.deadline_utc,
            confidence=request.confidence,
            max_retries=request.max_retries,
            parent_goal_id=goal_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"status": "success", "subgoal": subgoal}


# ─────────────────────────────────────────────────────────────────────────────
# Principal / Identity Endpoints (M32 Identity System)
# ─────────────────────────────────────────────────────────────────────────────

@telemetry_router.post("/principals/register")
def post_register_principal(request: RegisterPrincipalRequest) -> Dict[str, Any]:
    """Registers a new principal."""
    _require_ledger()
    from backend.core.governance.identity_registry import IdentityRegistry, PrincipalValidationError
    registry = IdentityRegistry(KERNEL.ledger)
    if registry.resolve(request.name) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Principal with name '{request.name}' already exists.",
        )
    try:
        principal = registry.register(
            name=request.name,
            principal_type=request.principal_type,
            trust_level=request.trust_level,
            capabilities=request.capabilities,
            metadata=request.metadata,
            principal_id=request.principal_id,
            public_key=request.public_key,
        )
    except PrincipalValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "success", "principal": principal.to_dict()}


@telemetry_router.get("/principals/list")
def get_list_principals(
    principal_type: str | None = None,
    active_only: bool = True,
) -> Dict[str, Any]:
    """Lists all registered principals, filterable by type and active status."""
    _require_ledger()
    from backend.core.governance.identity_registry import IdentityRegistry
    registry = IdentityRegistry(KERNEL.ledger)
    principals = registry.list(principal_type=principal_type, active_only=active_only)
    return {"principals": [p.to_dict() for p in principals], "count": len(principals)}


@telemetry_router.get("/principals/{principal_id}")
def get_principal_info(principal_id: str) -> Dict[str, Any]:
    """Retrieves detailed information for a specific principal by ID."""
    _require_ledger()
    from backend.core.governance.identity_registry import IdentityRegistry
    registry = IdentityRegistry(KERNEL.ledger)
    principal = registry.get(principal_id)
    if principal is None:
        raise HTTPException(status_code=404, detail=f"Principal '{principal_id}' not found.")
    return {"principal": principal.to_dict()}


@telemetry_router.post("/principals/{principal_id}/deactivate")
def post_deactivate_principal(principal_id: str) -> Dict[str, Any]:
    """Soft-deletes/deactivates a principal by ID."""
    _require_ledger()
    from backend.core.governance.identity_registry import IdentityRegistry
    registry = IdentityRegistry(KERNEL.ledger)
    principal = registry.get(principal_id)
    if principal is None:
        raise HTTPException(status_code=404, detail=f"Principal '{principal_id}' not found.")
    registry.deactivate(principal_id)
    return {"status": "success", "principal_id": principal_id}


# ─── Audit Ledger endpoints (M33 Immutable Audit Ledger) ───────────────────

@telemetry_router.get("/audit/logs")
def get_audit_logs(
    principal_id: str | None = None,
    action: str | None = None,
    decision: str | None = None,
) -> Dict[str, Any]:
    """Retrieves and optionally filters the chained audit log entries."""
    _require_ledger()
    from backend.core.governance.audit_ledger import AuditLedger
    ledger = AuditLedger(KERNEL.ledger)
    entries = ledger.load_audit_entries()

    if principal_id:
        p_lower = principal_id.lower().strip()
        entries = [e for e in entries if e.get("principal_id", "").lower() == p_lower]
    if action:
        act_lower = action.lower().strip()
        entries = [e for e in entries if e.get("action", "").lower() == act_lower]
    if decision:
        dec_upper = decision.upper().strip()
        entries = [e for e in entries if e.get("decision", "").upper() == dec_upper]

    return {"status": "success", "logs": entries, "count": len(entries)}


@telemetry_router.get("/audit/verify")
def get_audit_verify() -> Dict[str, Any]:
    """Validates the cryptographic hash-chain integrity of the audit ledger."""
    _require_ledger()
    from backend.core.governance.audit_ledger import AuditLedger
    ledger = AuditLedger(KERNEL.ledger)
    valid, reason = ledger.validate_ledger_integrity()
    return {"status": "success", "valid": valid, "reason": reason}


# ─── Capability Negotiation Endpoints (M35 Dynamic Negotiation) ──────────────

class NegotiationRequest(BaseModel):
    principal_id: str
    capability: str
    reason: str
    duration_seconds: float = 60.0
    delegation_token_id: str | None = None


@telemetry_router.post("/governance/negotiate")
def post_negotiate_capability(request: NegotiationRequest) -> Dict[str, Any]:
    """Requests a temporary capability lease, evaluating auto-approval criteria."""
    _require_ledger()
    from backend.core.governance.capability_negotiator import CapabilityNegotiator
    return CapabilityNegotiator.request_capability(
        principal_id=request.principal_id,
        capability=request.capability,
        reason=request.reason,
        duration_seconds=request.duration_seconds,
        delegation_token_id=request.delegation_token_id,
    )


@telemetry_router.get("/governance/contracts")
def get_active_contracts_api(principal_id: str) -> Dict[str, Any]:
    """Retrieves all active capability contracts for a principal."""
    _require_ledger()
    from backend.core.governance.capability_negotiator import CapabilityNegotiator
    contracts = CapabilityNegotiator.get_active_contracts(principal_id)
    return {"status": "success", "contracts": contracts, "count": len(contracts)}


@telemetry_router.post("/governance/contracts/{contract_id}/approve")
def post_approve_contract(contract_id: str) -> Dict[str, Any]:
    """Manually approves an escalation capability request."""
    _require_ledger()
    from backend.core.governance.capability_negotiator import CapabilityNegotiator
    return CapabilityNegotiator.approve_request(contract_id)


@telemetry_router.post("/governance/contracts/{contract_id}/reject")
def post_reject_contract(contract_id: str) -> Dict[str, Any]:
    """Manually rejects or revokes a capability request."""
    _require_ledger()
    from backend.core.governance.capability_negotiator import CapabilityNegotiator
    return CapabilityNegotiator.reject_request(contract_id)


@telemetry_router.get("/self-model/state")
def get_self_model_state_api() -> Dict[str, Any]:
    """Exposes real-time self-model introspection state (Capabilities, Limitations, Resources, Confidence, Performance)."""
    from backend.core.self_model import SelfModel
    return SelfModel.get_self_model_state()


@telemetry_router.get("/telemetry/tools-reputation")
def get_tools_reputation_api() -> Dict[str, Any]:
    """Retrieves all active tool reliability and utility scores."""
    from backend.core.tool_reliability import ToolReliabilityTracker
    return ToolReliabilityTracker.get_all_reliability()


@telemetry_router.get("/telemetry/agents-reputation")
def get_agents_reputation_api() -> Dict[str, Any]:
    """Retrieves all agent trust scores and execution telemetry logs."""
    from backend.core.agent_reputation import AgentReputationTracker
    agents = ["planner", "coder", "browser", "desktop", "researcher", "voice", "vision"]
    reputations = {}
    for agent in agents:
        reputations[agent] = AgentReputationTracker.get_reputation(agent)
    return reputations



