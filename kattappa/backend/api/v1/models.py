from fastapi import APIRouter, WebSocket, Header, HTTPException, Body
from typing import Any
from backend.api.v1.common import *

models_router = APIRouter(tags=["Models"])

@models_router.get("/agents")
def list_agents() -> dict[str, object]:
    from backend.core.agent_registry import DEFAULT_REGISTRY
    return DEFAULT_REGISTRY.to_dict()



@models_router.get("/agents/{name}")
def get_agent(name: str) -> dict[str, object]:
    from backend.core.agent_registry import DEFAULT_REGISTRY
    agent = DEFAULT_REGISTRY.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"No agent named {name!r}")
    return agent.to_dict()



@models_router.post("/router/route")
def router_route(request: RouterRouteRequest) -> dict[str, object]:
    from backend.core.agent_router import DEFAULT_ROUTER
    try:
        return DEFAULT_ROUTER.route(request.prompt, mode=request.mode).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/consensus/decide")
def consensus_decide(request: ConsensusDecideRequest) -> dict[str, object]:
    from backend.core.consensus_engine import decide_from_dicts
    return decide_from_dicts(request.outputs, request.context).to_dict()



@models_router.post("/benchmark/run")
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



@models_router.post("/benchmark/compare")
def benchmark_compare(request: BenchmarkCompareRequest) -> dict[str, object]:
    from backend.core.benchmark_arena import BenchmarkArena
    return BenchmarkArena.compare_versions(
        current_run=request.current_run,
        previous_run=request.previous_run,
        floors=request.floors,
    )



@models_router.get("/benchmark/history")
def benchmark_history() -> dict[str, object]:
    from backend.core.benchmark_arena import BenchmarkArena
    return {"history": BenchmarkArena.load_history()}



@models_router.post("/benchmark/tools/evaluate")
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



@models_router.get("/benchmark/tools/history")
def tool_benchmark_history() -> dict[str, object]:
    from backend.core.benchmark_arena import BenchmarkArena

    return {"history": BenchmarkArena.load_tool_history()}



@models_router.post("/api/benchmark/continuous/run")
def run_continuous_benchmark() -> dict[str, object]:
    from backend.core.continuous_benchmark import ContinuousBenchmarkRunner
    return ContinuousBenchmarkRunner.run_suite()



@models_router.get("/api/benchmark/continuous/latest")
def get_latest_continuous_benchmark() -> dict[str, object]:
    from backend.core.continuous_benchmark import ContinuousBenchmarkRunner
    report = ContinuousBenchmarkRunner.get_latest_report()
    if not report:
        raise HTTPException(status_code=404, detail="No continuous benchmark runs found.")
    return report



@models_router.get("/api/benchmark/continuous/history")
def get_continuous_benchmark_history(limit: int = 50) -> dict[str, object]:
    from backend.core.continuous_benchmark import ContinuousBenchmarkRunner
    return {"history": ContinuousBenchmarkRunner.get_report_history(limit)}



@models_router.post("/proposal/observe")
def proposal_observe(request: ProposalObserveRequest) -> dict[str, object]:
    from backend.core.proposal_engine import ProposalEngine
    obs = ProposalEngine.observe_issue(request.issue, request.severity, request.metrics)
    hyps = ProposalEngine.reflect_on_observation(obs)
    return {"observation": obs, "hypotheses": hyps}



@models_router.post("/proposal/create")
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



@models_router.get("/proposal/list")
def proposal_list() -> dict[str, object]:
    from backend.core.proposal_engine import ProposalEngine
    return {"proposals": ProposalEngine.list_proposals()}



@models_router.post("/proposal/approve/{proposal_id}")
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



@models_router.post("/proposal/negative-knowledge")
def proposal_negative_knowledge(request: ProposalNegativeKnowledgeRequest) -> dict[str, object]:
    from backend.core.proposal_engine import ProposalEngine
    entry = ProposalEngine.register_negative_knowledge(request.title, request.reason)
    return {"entry": entry}



@models_router.get("/proposal/budget")
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



@models_router.post("/proposal/review/{proposal_id}")
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



@models_router.post("/proposal/record-result/{proposal_id}")
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



@models_router.get("/proposal/track-records")
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



@models_router.post("/sandbox/run-experiment/{proposal_id}")
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



@models_router.get("/sandbox/experiments")
def sandbox_list_experiments() -> dict[str, object]:
    from backend.core.sandbox_lab import ArtifactStore
    return {"experiments": ArtifactStore.load_experiments()}



@models_router.get("/sandbox/prs")
def sandbox_prs_score() -> dict[str, object]:
    from backend.core.sandbox_lab import ResultPackager
    return {"prs": ResultPackager.get_overall_prs()}



@models_router.post("/deployment/assess/{proposal_id}")
def deployment_assess(proposal_id: str, request: DeploymentAssessRequest) -> dict[str, object]:
    from backend.core.deployment_advisor import DeploymentAdvisor
    return DeploymentAdvisor.assess_deployment(proposal_id, request.benchmark_scores, request.baseline_scores)



@models_router.post("/deployment/canary/step/{proposal_id}")
def deployment_canary_step(proposal_id: str, request: CanaryStepRequest) -> dict[str, object]:
    from backend.core.deployment_advisor import CanaryReleaseCoordinator
    return CanaryReleaseCoordinator.advance_canary(
        proposal_id,
        request.simulated_anomaly,
        request.simulated_held_out_regression
    )



@models_router.post("/deployment/rollback/{proposal_id}")
def deployment_rollback(proposal_id: str, request: RollbackRequest) -> dict[str, object]:
    from backend.core.deployment_advisor import AutomaticRollbackEngine
    return AutomaticRollbackEngine.rollback(proposal_id, request.reason)



@models_router.post("/research/analyze")
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



@models_router.get("/research/results")
def research_results() -> list[dict[str, Any]]:
    from backend.core.research_agent import ResearchAgent
    try:
        return ResearchAgent.list_results()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@models_router.post("/sandbox/run-experiment-v2/{proposal_id}")
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



@models_router.get("/goals")

@models_router.get("/api/goals")
def goals_status() -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    return GoalManager.status()



@models_router.get("/goals/list")

@models_router.get("/api/goals/list")
def goals_list() -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    return {"items": GoalManager.list_goals()}



@models_router.post("/goals")

@models_router.post("/api/goals")
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



@models_router.post("/goals/{goal_id}/approve")

@models_router.post("/api/goals/{goal_id}/approve")
def goals_approve(goal_id: str) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return {"item": GoalMemory.update_goal_status(goal_id, "APPROVED", "Approved by user/executive")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/goals/{goal_id}/reaffirm")

@models_router.post("/api/goals/{goal_id}/reaffirm")
def goals_reaffirm(goal_id: str) -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    try:
        return {"item": GoalManager.reaffirm(goal_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.get("/goals/{goal_id}/conflicts")

@models_router.get("/api/goals/{goal_id}/conflicts")
def goals_list_conflicts(goal_id: str) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return {"items": GoalMemory.get_conflicts(goal_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@models_router.post("/goals/conflicts")

@models_router.post("/api/goals/conflicts")
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



@models_router.post("/goals/conflicts/{conflict_id}/resolve")

@models_router.post("/api/goals/conflicts/{conflict_id}/resolve")
def goals_resolve_conflict(conflict_id: str, request: ConflictResolveRequest) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        GoalMemory.resolve_conflict(conflict_id, request.resolution_status)
        return {"status": "success"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.get("/goals/{goal_id}/values")

@models_router.get("/api/goals/{goal_id}/values")
def goals_list_values(goal_id: str) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return {"items": GoalMemory.get_values(goal_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@models_router.get("/goals/{goal_id}/drift")

@models_router.get("/api/goals/{goal_id}/drift")
def goals_check_drift(goal_id: str) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return GoalMemory.check_goal_drift(goal_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@models_router.post("/goals/{goal_id}/milestones")

@models_router.post("/api/goals/{goal_id}/milestones")
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



@models_router.get("/goals/active")

@models_router.get("/api/goals/active")
def goals_active() -> dict[str, object]:
    from backend.core.goal_manager import GoalManager
    return {"items": GoalManager.list_goals(status="ACTIVE")}



@models_router.get("/goals/metrics")

@models_router.get("/api/goals/metrics")
def goals_metrics() -> dict[str, object]:
    from backend.core.learning_dashboard import LearningDashboard
    try:
        return {"status": "ok", "data": LearningDashboard.goal_calibration_panel()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@models_router.get("/dashboard/goals/reflection")
def dashboard_goals_reflection() -> dict[str, object]:
    from backend.core.learning_dashboard import LearningDashboard
    try:
        return {"status": "ok", "data": LearningDashboard.goal_calibration_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/goals/{goal_id}/history")

@models_router.get("/api/goals/{goal_id}/history")
def goals_history(goal_id: str) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return {"items": GoalMemory.get_events(goal_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@models_router.get("/goals/policies/absolute")

@models_router.get("/api/goals/policies/absolute")
def goals_absolute_policies() -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    return {"policies": GoalMemory.ABSOLUTE_POLICIES}



@models_router.post("/goals/{goal_id}/update")

@models_router.post("/api/goals/{goal_id}/update")
def goals_update(goal_id: str, request: GoalUpdateRequest) -> dict[str, object]:
    from backend.core.goal_memory import GoalMemory
    try:
        return {"item": GoalMemory.update_goal_content(goal_id, request.title, request.description)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/goals/{goal_id}/complete")

@models_router.post("/api/goals/{goal_id}/complete")
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



@models_router.post("/goals/{goal_id}/{action}")

@models_router.post("/api/goals/{goal_id}/{action}")
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



@models_router.post("/api/ppm/projects")
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



@models_router.post("/api/ppm/milestones")
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



@models_router.post("/api/ppm/tasks")
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



@models_router.post("/api/ppm/blockers")
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



@models_router.post("/api/ppm/blockers/{blocker_id}/resolve")
def ppm_blockers_resolve(blocker_id: str) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        PersonalProjectManager.resolve_blocker(blocker_id)
        return {"status": "success"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/api/ppm/resources")
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



@models_router.post("/api/ppm/resources/consume")
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



@models_router.post("/api/ppm/projects/{project_id}/revisions")
def ppm_projects_revision(project_id: str, request: PPMRevisionLogRequest) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        PersonalProjectManager.log_revision(project_id, request.author, request.summary)
        return {"status": "success"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/api/ppm/projects/{project_id}/complete")
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



@models_router.get("/api/ppm/projects/{project_id}")
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



@models_router.get("/api/ppm/projects/{project_id}/report")
def ppm_projects_report(project_id: str) -> dict[str, object]:
    from backend.core.personal_project_manager import PersonalProjectManager
    try:
        return {"report": PersonalProjectManager.reflect_on_project(project_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@models_router.get("/projects")

@models_router.get("/api/projects")
def projects_list() -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    return {"items": ProjectManagerV2.list_projects()}



@models_router.post("/projects")

@models_router.post("/api/projects")
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



@models_router.get("/projects/ecosystem")
def get_project_ecosystem() -> dict[str, object]:
    return project_ecosystem()



@models_router.get("/projects/improvement-agents")
def get_project_improvement_agents() -> dict[str, object]:
    return project_improvement_agents()



@models_router.post("/projects/improvement-agents/observe")
def observe_project_improvement_agents_endpoint(
    request: ProjectImprovementObserveRequest,
) -> dict[str, object]:
    return observe_project_improvement_agents(run_status=request.run_status)



@models_router.post("/projects/improvement-agents/check-shared")
def check_shared_project_improvements() -> dict[str, object]:
    return check_git_shared_improvements()



@models_router.get("/projects/{project_id}")

@models_router.get("/api/projects/{project_id}")
def projects_get_hierarchy(project_id: str) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        proj = ProjectManagerV2.get_project_hierarchy(project_id)
        if not proj:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return {"item": proj}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@models_router.get("/projects/{project_id}/simulation")

@models_router.get("/api/projects/{project_id}/simulation")
def projects_simulate(project_id: str) -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine
    try:
        return {"report": SimulationEngine.simulate_project(project_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@models_router.post("/projects/{project_id}/goals")

@models_router.post("/api/projects/{project_id}/goals")
def projects_add_goal(project_id: str, request: ProjectGoalAddRequest) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        ProjectManagerV2.add_goal_to_project(request.goal_id, project_id)
        return {"status": "success", "item": ProjectManagerV2.get_project(project_id)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/projects/{project_id}/decisions")

@models_router.post("/api/projects/{project_id}/decisions")
def projects_add_decision(project_id: str, request: ProjectDecisionRequest) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        ProjectManagerV2.log_project_decision(project_id, request.title, request.description, request.rationale)
        return {"status": "success", "item": ProjectManagerV2.get_project(project_id)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/projects/{project_id}/dependencies")

@models_router.post("/api/projects/{project_id}/dependencies")
def projects_add_dependency(project_id: str, request: ProjectDependencyRequest) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        ProjectManagerV2.add_project_dependency(project_id, request.depends_on_project_id)
        return {"status": "success", "item": ProjectManagerV2.get_project(project_id)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.get("/projects/{project_id}/logs")

@models_router.get("/api/projects/{project_id}/logs")
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



@models_router.post("/projects/{project_id}/transition/{status}")

@models_router.post("/api/projects/{project_id}/transition/{status}")
def projects_transition_status(project_id: str, status: str) -> dict[str, object]:
    from backend.core.project_manager_v2 import ProjectManagerV2
    try:
        return {"item": ProjectManagerV2.update_project_status(project_id, status)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc





@models_router.get("/reflection")
def reflection_status(status: str | None = None) -> dict[str, object]:
    from backend.core.reflection_engine import ReflectionEngine
    if status:
        return {"items": ReflectionEngine.list_reflections(status=status)}
    return ReflectionEngine.status()



@models_router.post("/reflection/propose")
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



@models_router.post("/reflection/{reflection_id}/{action}")
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



@models_router.get("/capabilities")
def capabilities_status() -> dict[str, object]:
    from backend.core.capability_graph import CapabilityGraph
    return {"status": CapabilityGraph.status(), "items": CapabilityGraph.list_capabilities()}



@models_router.post("/capabilities")
def capabilities_register(request: CapabilityRegisterRequest) -> dict[str, object]:
    from backend.core.capability_graph import CapabilityGraph
    try:
         return {"item": CapabilityGraph.register(
            request.name, request.kind, available=request.available,
            depends_on=request.depends_on, alternatives=request.alternatives, risk=request.risk,
         )}
    except ValueError as exc:
         raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/capabilities/assess")
def capabilities_assess(request: CapabilityAssessRequest) -> dict[str, object]:
    from backend.core.capability_graph import CapabilityGraph
    return CapabilityGraph.assess(request.goal, request.required)



@models_router.post("/trust/assess")
def trust_assess(request: TrustAssessRequest) -> dict[str, object]:
    from backend.core.trust_evidence import assess_from_dicts
    return assess_from_dicts(request.statement, request.evidence).to_dict()



@models_router.get("/world")
def world_status() -> dict[str, object]:
    from backend.core.world_model import WorldModel
    return WorldModel.status()



@models_router.post("/world/entity")
def world_add_entity(request: WorldEntityRequest) -> dict[str, object]:
    from backend.core.world_model import WorldModel
    try:
        return {"item": WorldModel.add_entity(
            request.name, request.type, status=request.status, attributes=request.attributes)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/world/relation")
def world_add_relation(request: WorldRelationRequest) -> dict[str, object]:
    from backend.core.world_model import WorldModel
    try:
        return {"item": WorldModel.add_relation(request.src, request.dst, request.relation)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.get("/world/impact/{name}")
def world_impact(name: str) -> dict[str, object]:
    from backend.core.world_model import WorldModel
    try:
        return WorldModel.impact_of(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc



@models_router.post("/simulate")
def simulate(request: SimulateRequest) -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine
    return SimulationEngine.simulate_dict(
        request.scenario, trials=request.trials, seed=request.seed).to_dict()



@models_router.post("/simulate/plan")
def simulate_plan(request: PlanSimulationRequest) -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine

    return SimulationEngine.simulate_plan(
        request.plan,
        goal=request.goal,
        workflow_id=request.workflow_id,
        context=request.context,
    ).to_dict()



@models_router.post("/simulate/counterfactual")
def simulate_counterfactual(request: PlanSimulationRequest) -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine
    return SimulationEngine.run_counterfactual_simulations(
        request.plan,
        goal=request.goal,
        workflow_id=request.workflow_id
    )



@models_router.post("/simulate/forecast")
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



@models_router.post("/simulate/outcome")
def record_outcome(request: DecisionOutcomeRequest) -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine
    SimulationEngine.record_decision_outcome(
        request.decision_id,
        request.actual_success,
        request.actual_cost,
        request.actual_time
    )
    return {"status": "success", "decision_id": request.decision_id}



@models_router.post("/simulate/recalibrate")
def recalibrate_simulations() -> dict[str, object]:
    from backend.core.simulation_engine import SimulationEngine
    return SimulationEngine.recalibrate_from_ledger()



@models_router.post("/research/ingest")
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



@models_router.get("/research/proposals")
def research_proposals() -> list[dict[str, object]]:
    from backend.core.research_loop import ResearchLoop
    return ResearchLoop.list_proposals()



@models_router.post("/research/evaluate")
def research_evaluate(request: ResearchEvaluateRequest) -> dict[str, object]:
    from backend.core.research_loop import ResearchLoop
    return ResearchLoop.evaluate_experiment_candidate(
        experiment_id=request.experiment_id,
        run_results=request.run_results
    )



@models_router.post("/benchmark/variants/generate")
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



@models_router.get("/benchmark/variants/{suite_id}")
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


@models_router.post("/research/reproduce/{claim_id}")
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



@models_router.get("/research/reproduce/queue")
def research_reproduce_queue() -> dict[str, object]:
    """List all experiments queued for human-triggered reproduction."""
    from backend.core.claim_reproduction_engine import ClaimReproductionEngine
    queued = ClaimReproductionEngine.list_queued()
    return {"queued_count": len(queued), "experiments": queued}



@models_router.get("/research/reproduce/results")
def research_reproduce_results(limit: int = 50) -> dict[str, object]:
    """List completed reproduction experiment results."""
    from backend.core.claim_reproduction_engine import ClaimReproductionEngine
    results = ClaimReproductionEngine.list_results(limit=limit)
    return {"results": results}


# ── Step 21: Self-Improvement Governance ─────────────────────────────────────


@models_router.post("/governance/submit")
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



@models_router.get("/governance/pending")
def governance_pending() -> dict[str, object]:
    """List all proposals awaiting human review."""
    from backend.core.self_improvement_governance import SelfImprovementGovernance
    proposals = SelfImprovementGovernance.list_pending()
    return {"pending_count": len(proposals), "proposals": proposals}



@models_router.post("/governance/approve/{proposal_id}")
def governance_approve(proposal_id: str, request: GovernanceReviewRequest) -> dict[str, object]:
    """Human approves a pending governance proposal."""
    from backend.core.self_improvement_governance import SelfImprovementGovernance
    success = SelfImprovementGovernance.approve(proposal_id, request.reviewer_id)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found or not pending")
    return {"proposal_id": proposal_id, "status": "approved", "reviewer_id": request.reviewer_id}



@models_router.post("/governance/reject/{proposal_id}")
def governance_reject(proposal_id: str, request: GovernanceReviewRequest) -> dict[str, object]:
    """Human rejects a pending governance proposal."""
    from backend.core.self_improvement_governance import SelfImprovementGovernance
    success = SelfImprovementGovernance.reject(proposal_id, request.reviewer_id, request.reason)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found or not pending")
    return {"proposal_id": proposal_id, "status": "rejected", "reviewer_id": request.reviewer_id}



@models_router.get("/governance/proposals")
def governance_all_proposals(limit: int = 100) -> dict[str, object]:
    """Return all governance proposals (any status), newest first."""
    from backend.core.self_improvement_governance import SelfImprovementGovernance
    proposals = SelfImprovementGovernance.list_all(limit=limit)
    return {"total": len(proposals), "proposals": proposals}



@models_router.get("/governance/audit/{proposal_id}")
def governance_audit_log(proposal_id: str) -> dict[str, object]:
    """Return the full audit trail for a governance proposal."""
    from backend.core.self_improvement_governance import SelfImprovementGovernance
    log = SelfImprovementGovernance.get_audit_log(proposal_id)
    return {"proposal_id": proposal_id, "audit_log": log}


# ── Council of Perspectives (Step 15.5 + Council v2) ─────────────────────────


@models_router.post("/council/deliberate")
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



@models_router.post("/council/deliberate/quick")
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



@models_router.get("/council/decisions")
def council_decisions(limit: int = 50) -> dict[str, object]:
    """List all council deliberation decisions from the ledger, newest first."""
    from backend.core.council_session import CouncilSession
    decisions = CouncilSession.list_decisions(limit=limit)
    return {"total": len(decisions), "decisions": decisions}



@models_router.get("/council/decision/{decision_id}")
def council_decision_detail(decision_id: str) -> dict[str, object]:
    """Retrieve full details of a single council decision including votes and audit findings."""
    from backend.core.council_session import CouncilSession
    decision = CouncilSession.get_decision(decision_id)
    if not decision:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Council decision {decision_id} not found")
    return decision



@models_router.get("/council/performance")
def council_performance() -> dict[str, object]:
    """Performance report: council approval/rejection rates and Arena outcome accuracy."""
    from backend.core.council_session import CouncilPerformanceReport
    return CouncilPerformanceReport.generate()



@models_router.post("/council/benchmark/validate")
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



@models_router.post("/council/benchmark/{decision_id}")
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



@models_router.post("/personality-council/deliberate")
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



@models_router.get("/personality-council/session/{session_id}")
def personality_council_session(session_id: str) -> dict[str, object]:
    """Retrieve a persisted Step 20 council session."""
    from backend.core.council import PersonalityCouncil
    session = PersonalityCouncil.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Personality council session {session_id} not found")
    return session



@models_router.post("/personality-council/outcomes/{outcome_id}")
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



@models_router.get("/personality-council/performance")
def personality_council_performance() -> dict[str, object]:
    """Return Step 20 council calibration and outcome coverage."""
    from backend.core.council import PersonalityCouncil
    return PersonalityCouncil.performance()



@models_router.post("/distill")
def distill(request: DistillRequest) -> dict[str, object]:
    from backend.core.knowledge_distillation import KnowledgeDistiller
    return KnowledgeDistiller.distill(
        request.observations, min_cluster=request.min_cluster,
        principle_hints=request.principle_hints).to_dict()



@models_router.get("/value/profiles")
def value_profiles() -> dict[str, object]:
    from backend.core.value_engine import PROFILES
    return {"profiles": {p.value: w for p, w in PROFILES.items()}}



@models_router.post("/value/score")
def value_score(request: ValueScoreRequest) -> dict[str, object]:
    from backend.core.value_engine import PlanSignals, ValueEngine
    return ValueEngine.score_plan(PlanSignals.from_dict(request.signals))



@models_router.post("/value/rank")
def value_rank(request: ValueRankRequest) -> dict[str, object]:
    from backend.core.value_engine import PlanSignals, ValueEngine, ValueProfile
    plans = [PlanSignals.from_dict(p) for p in request.plans]
    try:
        profile = ValueProfile.coerce(request.profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ValueEngine.rank(plans, profile).to_dict()



@models_router.get("/value/drift")
def value_drift() -> dict[str, object]:
    from backend.core.value_engine import ValueDriftMonitor
    return ValueDriftMonitor.report()

@models_router.get("/health")
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



@models_router.get("/ready")
def ready_check() -> dict[str, str]:
    return {"status": "ready"}



@models_router.get("/free-stack")
def free_stack() -> dict[str, object]:
    return free_stack_report()



@models_router.get("/free-tools")
def free_tools() -> dict[str, object]:
    return free_tool_decision_report()



@models_router.get("/ai-engine/local-models")
def ai_engine_local_models() -> dict[str, object]:
    return local_model_profiles()



@models_router.get("/ai-engine/airllm/status")
def ai_engine_airllm_status() -> dict[str, object]:
    return airllm_status()



@models_router.post("/ai-engine/airllm/generate")
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



@models_router.get("/writing/status")
def writing_engine_status() -> dict[str, object]:
    return writing_status()



@models_router.post("/writing/check")
def writing_check(request: WritingCheckRequest) -> dict[str, object]:
    return check_grammar(request.text)



@models_router.post("/writing/rewrite")
def writing_rewrite(request: WritingRewriteRequest) -> dict[str, object]:
    return improve_text(request.text, tone=request.tone)



@models_router.get("/toolbox/replacements")
def toolbox_replacements() -> dict[str, object]:
    return toolbox_replacement_report()



@models_router.post("/creator/deck")
def creator_deck(request: LocalDeckRequest) -> dict[str, object]:
    return create_local_deck_outline(
        request.topic,
        audience=request.audience,
        project=request.project,
        slide_count=request.slide_count,
    )



@models_router.post("/creator/diagram")
def creator_diagram(request: LocalDiagramRequest) -> dict[str, object]:
    return create_mermaid_diagram(request.text, diagram_type=request.diagram_type)



@models_router.post("/context/compress")
def context_compress(request: ContextCompressRequest) -> dict[str, object]:
    return compress_context(request.text, max_points=request.max_points)



@models_router.post("/creator/code-review")
def creator_code_review(request: LocalReviewRequest) -> dict[str, object]:
    return local_code_review(request.diff_text, project=request.project)



@models_router.post("/creator/gsd-workflow")
def creator_gsd_workflow(request: LocalGsdWorkflowRequest) -> dict[str, object]:
    return create_gsd_workflow(request.goal, project=request.project)



@models_router.post("/creator/document-markdown")
def creator_document_markdown(request: DocumentMarkdownRequest) -> dict[str, object]:
    return convert_document_text_to_markdown(request.filename, request.text)



@models_router.post("/creator/marketing-kit")
def creator_marketing_kit(request: MarketingKitRequest) -> dict[str, object]:
    return create_marketing_kit(
        request.brand,
        request.product,
        audience=request.audience,
        channel=request.channel,
    )



@models_router.post("/web-research/extract")
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



@models_router.get("/simulation/status")
def simulation_lab_status() -> dict[str, object]:
    return simulation_status()



@models_router.post("/simulation/run")
def simulation_lab_run(request: SimulationRequest) -> dict[str, object]:
    return run_simulation(request.seed, request.horizon)



@models_router.get("/system/hardware-requirements")
def system_hardware_requirements() -> dict[str, object]:
    return hardware_requirements()



@models_router.get("/system/platform-support")
def system_platform_support() -> dict[str, object]:
    return platform_support_report()



@models_router.get("/system/adaptive-profile")
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



@models_router.get("/cluster/plan")
def kattappa_cluster_plan() -> dict[str, object]:
    return cluster_plan()



@models_router.get("/cluster/status")
def kattappa_cluster_status() -> dict[str, object]:
    return cluster_runtime_status()



@models_router.get("/cluster/nodes")
def kattappa_cluster_nodes() -> dict[str, object]:
    return {"items": list_paired_nodes()}



@models_router.post("/cluster/nodes")
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



@models_router.delete("/cluster/nodes/{node_id}")
def kattappa_remove_cluster_node(node_id: str) -> dict[str, object]:
    if not remove_paired_node(node_id):
        raise HTTPException(status_code=404, detail="Paired node not found")
    return {"removed": True, "node_id": node_id}



@models_router.get("/cluster/discovery-targets")
def kattappa_cluster_discovery_targets() -> dict[str, object]:
    return {"items": list_discovery_targets()}



@models_router.post("/cluster/discovery-targets")
def kattappa_register_cluster_discovery_target(
    request: ClusterDiscoveryTargetRequest,
) -> dict[str, object]:
    try:
        item = register_discovery_target(request.name, request.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}



@models_router.delete("/cluster/discovery-targets/{target_id}")
def kattappa_remove_cluster_discovery_target(target_id: str) -> dict[str, object]:
    if not remove_discovery_target(target_id):
        raise HTTPException(status_code=404, detail="Discovery target not found")
    return {"removed": True, "target_id": target_id}



@models_router.post("/cluster/tasks/route")
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



@models_router.post("/cluster/tasks/bids")
def kattappa_cluster_task_bids(request: ClusterBidRequest) -> dict[str, object]:
    try:
        return collect_worker_bids(request.message, request.task_kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/cluster/worker/bid")
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



@models_router.get("/cluster/public/status")
def kattappa_public_worker_status() -> dict[str, object]:
    return public_worker_status()



@models_router.post("/cluster/public/bid")
def kattappa_public_worker_bid(request: ClusterPublicBidRequest) -> dict[str, object]:
    return public_worker_capability_bid(
        request.bid_id,
        request.task_kind,
        capability_hint=dict(request.capability_hint),
        origin_node=dict(request.origin_node),
    )



@models_router.post("/cluster/public/tasks")
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



@models_router.post("/cluster/worker/tasks")
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


@models_router.post("/cluster/hub/post-task")
def hub_post_task_endpoint(request: HubTaskRequest) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_post_task
    return hub_post_task(
        request.task_id,
        request.task_kind,
        request.min_cpu,
        request.min_ram,
    )



@models_router.get("/cluster/hub/pending-tasks")
def hub_pending_tasks_endpoint() -> dict[str, object]:
    from backend.core.cluster_runtime import hub_get_pending_tasks
    return {"tasks": hub_get_pending_tasks()}



@models_router.post("/cluster/hub/bid-task")
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



@models_router.get("/cluster/hub/tasks/{task_id}/bids")
def hub_get_bids_endpoint(task_id: str) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_get_bids
    return {"bids": hub_get_bids(task_id)}



@models_router.post("/cluster/hub/tasks/{task_id}/delegate")
def hub_delegate_task_endpoint(task_id: str, request: HubDelegateRequest) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_delegate_task
    success = hub_delegate_task(task_id, request.worker_id, request.message)
    if not success:
        raise HTTPException(status_code=400, detail="Task not found or not pending")
    return {"success": True}



@models_router.get("/cluster/hub/tasks/{task_id}/payload")
def hub_get_payload_endpoint(task_id: str, worker_id: str) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_get_payload
    payload = hub_get_payload(task_id, worker_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="No delegated task found for this worker")
    return payload



@models_router.post("/cluster/hub/tasks/{task_id}/submit-result")
def hub_submit_result_endpoint(task_id: str, request: HubResultSubmit) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_submit_result
    success = hub_submit_result(task_id, request.worker_id, request.result, request.error)
    if not success:
        raise HTTPException(status_code=400, detail="Task not delegated to this worker")
    return {"success": True}



@models_router.get("/cluster/hub/tasks/{task_id}/result")
def hub_get_result_endpoint(task_id: str) -> dict[str, object]:
    from backend.core.cluster_runtime import hub_get_result
    res = hub_get_result(task_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return res



@models_router.get("/cluster/prometheus/health")
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



@models_router.post("/cluster/hub/mimo-code")
def cluster_hub_mimo_code(request: MimoCodeRequest) -> dict[str, object]:
    from backend.core.mimo_agent import MimoCodeAgent
    agent = MimoCodeAgent()
    result = agent.generate_code_patch(request.prompt, request.file_path)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result




@models_router.get("/finance/kronos/status")
def finance_kronos_status() -> dict[str, object]:
    return kronos_status()



@models_router.post("/finance/forecast")
def finance_forecast(request: FinanceForecastRequest) -> dict[str, object]:
    candles = [candle.model_dump() for candle in request.candles]
    try:
        return forecast_ohlcv(
            candles, horizon=request.horizon, use_kronos=request.use_kronos
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/finance/forecast-csv")
def finance_forecast_csv(request: FinanceCsvForecastRequest) -> dict[str, object]:
    try:
        candles = load_ohlcv_csv(request.path)
        return forecast_ohlcv(
            candles, horizon=request.horizon, use_kronos=request.use_kronos
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/finance/compare")
def finance_compare(request: FinanceForecastRequest) -> dict[str, object]:
    candles = [candle.model_dump() for candle in request.candles]
    try:
        return compare_forecasts(candles, horizon=request.horizon)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.post("/finance/compare-csv")
def finance_compare_csv(request: FinanceCsvForecastRequest) -> dict[str, object]:
    try:
        candles = load_ohlcv_csv(request.path)
        return compare_forecasts(candles, horizon=request.horizon)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@models_router.get("/source-policy")
def source_policy() -> dict[str, object]:
    return source_first_policy()



@models_router.get("/tool-scout")
def tool_scout(limit: int = 25) -> dict[str, object]:
    return scout_status(limit=limit)



@models_router.post("/tool-scout/run")
def run_tool_scout(request: ToolScoutRequest) -> dict[str, object]:
    return scout_for_task(request.task, request.outcome)



@models_router.post("/tool-scout/{report_id}/adopt")
def adopt_tool_scout_report(report_id: str) -> dict[str, object]:
    result = request_tool_adoption(report_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Tool scout report not found")
    return result



@models_router.get("/tool-adoptions")
def tool_adoptions(limit: int = 25) -> dict[str, object]:
    return list_tool_adoptions(limit=limit)



@models_router.post("/tool-adoptions/approved/{approval_id}")
def continue_tool_adoption(approval_id: str) -> dict[str, object]:
    return continue_tool_adoption_for_approval(approval_id)



@models_router.post("/install/missing/request")
def request_missing_installs() -> dict[str, object]:
    return request_missing_install_approval()



@models_router.post("/install/approved/{approval_id}")
def run_approved_installs(approval_id: str) -> dict[str, object]:
    return run_approved_install_job(approval_id)



@models_router.get("/capability-ladder")
def capability_ladder() -> dict[str, object]:
    return build_capability_ladder()



@models_router.get("/builder/profile")
def get_builder_profile() -> dict[str, object]:
    return builder_profile()



@models_router.get("/builder/codex-parity")
def get_codex_parity() -> dict[str, object]:
    return codex_parity_report()



@models_router.get("/builder/analytics")
def get_builder_analytics() -> dict[str, object]:
    return local_builder_analytics()



@models_router.get("/builder/workspace-map")
def get_workspace_map(limit: int = 80) -> dict[str, object]:
    return workspace_map(limit=limit)



@models_router.get("/project-index")
def project_index(limit: int = 220) -> dict[str, object]:
    return build_project_index(limit=limit)



@models_router.get("/project-index/search")
def project_index_search(q: str, limit: int = 30) -> dict[str, object]:
    return search_project_index(q, limit=limit)




@models_router.get("/action-memory/status")
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



@models_router.post("/action-memory/actions")
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



@models_router.get("/action-memory/actions/recent")
def action_memory_recent(limit: int = 100) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    return {"items": _action_records_payload(ActionMemory.get_recent_actions(limit=limit))}



@models_router.get("/action-memory/actions/successful")
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



@models_router.get("/action-memory/actions/failed")
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



@models_router.get("/action-memory/actions/similar")
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



@models_router.get("/action-memory/agents/{agent}/statistics")
def action_memory_agent_statistics(agent: str) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    return {"item": ActionMemory.get_agent_statistics(agent).to_dict()}



@models_router.get("/action-memory/workflows/{workflow_id}/actions")
def action_memory_workflow_actions(workflow_id: str, limit: int = 500) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    return {"items": _action_records_payload(ActionMemory.get_workflow_actions(workflow_id, limit=limit))}



@models_router.patch("/action-memory/actions/{action_id}")
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



@models_router.get("/action-memory/actions/{action_id}")
def action_memory_get(action_id: str) -> dict[str, object]:
    from backend.core.action_memory import ActionMemory

    item = ActionMemory.get_action(action_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Action memory record not found")
    return {"item": item.to_dict()}



@models_router.post("/long-tasks")
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



@models_router.get("/long-tasks")
def long_tasks(status: str | None = None, limit: int = 25) -> dict[str, object]:
    return {"items": memory.list_long_tasks(status=status, limit=limit)}



@models_router.get("/long-tasks/search")
def search_long_tasks(q: str, limit: int = 5) -> dict[str, object]:
    return {"items": memory.find_relevant_long_tasks(q, limit=limit)}



@models_router.post("/long-tasks/{task_id}")
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



@models_router.post("/long-tasks/{task_id}/resume")
def resume_task(task_id: str) -> dict[str, object]:
    result = resume_long_task(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Long task not found")
    return result



@models_router.post("/operator/plan")
def operator_plan(request: OperatorPlanRequest) -> dict[str, object]:
    return {"plan": build_operator_plan(request.message, selected_agent=None)}



@models_router.get("/skill-evaluations")
def skill_evaluations(
    skill_id: str | None = None, limit: int = 50
) -> dict[str, object]:
    return {"items": memory.list_skill_evaluations(skill_id=skill_id, limit=limit)}



@models_router.post("/skill-evaluations")
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



@models_router.get("/logs")
def logs(limit: int = 100) -> dict[str, object]:
    return {"lines": read_log(limit=limit)}



@models_router.get("/dashboard/executive")
def dashboard_executive() -> dict[str, object]:
    """Three-panel executive summary in governance priority order."""
    try:
        return {"status": "ok", "data": LearningDashboard.executive_summary()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/dashboard/executive-calibration")
def dashboard_executive_calibration() -> dict[str, object]:
    """Executive calibration panel for self-awareness metrics."""
    try:
        return {"status": "ok", "data": LearningDashboard.executive_calibration_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/dashboard/proposals")
def dashboard_proposals() -> dict[str, object]:
    """Proposal funnel with status breakdown and workflow backlog."""
    try:
        return {"status": "ok", "data": LearningDashboard.proposals_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/dashboard/experiments")
def dashboard_experiments() -> dict[str, object]:
    """Experiment list with sandbox pass rate and orphan count."""
    try:
        return {"status": "ok", "data": LearningDashboard.experiments_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/dashboard/benchmarks")
def dashboard_benchmarks() -> dict[str, object]:
    """Per-category benchmark scores with floors and recent history."""
    try:
        return {"status": "ok", "data": LearningDashboard.benchmarks_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/dashboard/research")
def dashboard_research() -> dict[str, object]:
    """Research summaries with trust level classification."""
    try:
        return {"status": "ok", "data": LearningDashboard.research_panel()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/dashboard/eroi")
def dashboard_eroi() -> dict[str, object]:
    """Production-anchored EROI with 95% confidence interval."""
    try:
        return {"status": "ok", "data": LearningDashboard.eroi()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/dashboard/metric-trust")
def dashboard_metric_trust() -> dict[str, object]:
    """Protected-Core metric trust map: MEASURED / DERIVED / PREDICTED."""
    try:
        return {"status": "ok", "data": LearningDashboard.metric_trust_map()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Burn-In Governance API  (Step 8.0 — State, Reset, Snapshot)
# ---------------------------------------------------------------------------


@models_router.get("/dashboard/burn-in/status")
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



@models_router.post("/dashboard/burn-in/reset")
def burn_in_reset(reviewer: str) -> dict[str, object]:
    """Reset system from AUDIT back to NORMAL. Human reviewer parameter required."""
    try:
        BurnInGovernance.reset_audit_mode(reviewer)
        return {"status": "ok", "message": f"Successfully reset audit mode to NORMAL by human reviewer '{reviewer}'."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.post("/dashboard/burn-in/snapshot")
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


@models_router.get("/dashboard/research-loop/status")
def research_loop_status() -> dict[str, object]:
    """Return status details of the daily research loop."""
    try:
        status_data = LearningDashboard.research_loop_status()
        return {"status": "ok", "data": status_data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/dashboard/research-loop/reputation")
def research_loop_reputation() -> dict[str, object]:
    """Return reputation database list of researched sources."""
    try:
        reputations = LearningDashboard.source_reputations()
        return {"status": "ok", "data": reputations}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.post("/dashboard/research-loop/trigger")
def research_loop_trigger() -> dict[str, object]:
    """Manually trigger an execution cycle of the research loop."""
    try:
        run_record = ResearchScheduler.trigger_run()
        return {"status": "ok", "data": run_record}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/dashboard/agent-society/reputation")
def dashboard_agent_society_reputation() -> dict[str, object]:
    """Returns the list of agents, their current reputation scores, and health status."""
    try:
        from backend.core.agent_society import AgentSociety
        reps = list(AgentSociety.load_reputations().values())
        return {"status": "ok", "data": reps}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/dashboard/agent-society/debates")
def dashboard_agent_society_debates() -> dict[str, object]:
    """Returns the historical log of agent debates, votes, consensus decisions, and veto occurrences."""
    try:
        from backend.core.learning_dashboard import LearningDashboard
        stats = LearningDashboard.agent_society_stats()
        return {"status": "ok", "data": stats}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/dashboard/executive-brain/missions")
def dashboard_executive_brain_missions() -> dict[str, object]:
    """Returns all missions, active status counts, weekly trend history, and long-horizon plans."""
    try:
        from backend.core.learning_dashboard import LearningDashboard
        stats = LearningDashboard.executive_brain_stats()
        return {"status": "ok", "data": stats}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.post("/dashboard/executive-brain/missions/create")
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



@models_router.get("/dashboard/executive-brain/evaluations")
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



@models_router.get("/dashboard/executive-brain/persistent-missions")
def dashboard_executive_brain_persistent_missions() -> dict[str, object]:
    """Returns persistent mission states, forecasts, RCA recovery queue, and cross learning."""
    try:
        from backend.core.learning_dashboard import LearningDashboard
        stats = LearningDashboard.executive_command_center_stats()
        return {"status": "ok", "data": stats}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.post("/dashboard/executive-brain/missions/recover")
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



@models_router.post("/dashboard/executive-brain/cross-learning/publish")
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

@models_router.get("/sandbox/constitution")
def sandbox_constitution() -> dict[str, object]:
    """Returns the three hardcoded safety rules (read-only introspection).

    Rule 1: Sandbox cannot authorize execution.
    Rule 2: Sandbox cannot create goals.
    Rule 3: Sandbox cannot rewrite constraints.
    """
    return {"status": "ok", "constitution": SandboxConstitution.as_dict()}



@models_router.post("/sandbox/evaluate")
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



@models_router.post("/sandbox/evaluate/project/{project_id}")
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



@models_router.post("/sandbox/resource-forecast/{project_id}")
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



@models_router.post("/sandbox/dependency-propagation/{project_id}")
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


@models_router.get("/hce/constitution")
def hce_constitution():
    """Return the six HCE constitutional safety rules (read-only)."""
    return {"status": "ok", "constitution": HCEConstitution.to_dict()}



@models_router.post("/hce/relationship")
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



@models_router.post("/hce/chapter")
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



@models_router.put("/hce/chapter/{chapter_id}/close")
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



@models_router.post("/hce/process")
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



@models_router.get("/hce/relationship/{relationship_id}/context")
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



@models_router.get("/hce/relationship/{relationship_id}/health")
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



@models_router.get("/hce/relationship/{relationship_id}/contradictions")
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



@models_router.get("/hce/relationship/{relationship_id}/narrative-arcs")
def hce_get_narrative_arcs(relationship_id: str):
    """Return all narrative arcs for a relationship."""
    try:
        arcs = HCEStore.get_narrative_arcs(relationship_id)
        return {"status": "ok", "narrative_arcs": arcs}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.get("/hce/memory-candidates")
def hce_memory_candidates(governance_status: str = "PENDING"):
    """List memory candidates by governance status (PENDING | COMMITTED | REJECTED)."""
    try:
        candidates = HCEStore.get_memory_candidates(governance_status=governance_status)
        return {"status": "ok", "candidates": candidates, "count": len(candidates)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.post("/hce/memory-candidates/{candidate_id}/commit")
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



@models_router.post("/hce/memory-candidates/{candidate_id}/reject")
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



@models_router.get("/hce/proposed-intents")
def hce_proposed_intents(status: str = "PENDING_USER_CONFIRMATION"):
    """List proposed intents by status."""
    try:
        intents = HCEStore.get_proposed_intents(status=status)
        return {"status": "ok", "intents": intents, "count": len(intents)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.post("/hce/proposed-intents/{proposal_id}/commit")
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

@models_router.get("/dashboard/cognitive/latest")
def get_cognitive_latest() -> dict[str, object]:
    """Returns the latest 11-tier dashboard metrics snapshot."""
    try:
        data = CognitiveDashboardManager.get_latest_snapshot()
        return {"status": "ok", "data": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@models_router.post("/dashboard/cognitive/snapshot")
def trigger_cognitive_snapshot() -> dict[str, object]:
    """Manually triggers a new system health snapshot sweep."""
    try:
        data = CognitiveDashboardManager.collect_snapshot()
        return {"status": "ok", "data": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@models_router.get("/dashboard/cognitive/health-events")
def get_health_events() -> dict[str, object]:
    """Returns all warning, critical, and info events logged in the ledger."""
    try:
        events = CognitiveDashboardManager.get_health_events()
        return {"status": "ok", "events": events}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@models_router.post("/dashboard/cognitive/health-events")
def log_health_event(payload: HealthEventRequest) -> dict[str, object]:
    """Logs a custom health event into the ledger."""
    try:
        evt_id = CognitiveDashboardManager.log_health_event(payload.severity, payload.source_module, payload.description)
        return {"status": "ok", "event_id": evt_id}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@models_router.post("/dashboard/cognitive/health-events/{event_id}/resolve")
def resolve_health_event(event_id: str) -> dict[str, object]:
    """Resolves an active health warning or critical alert."""
    try:
        resolved = CognitiveDashboardManager.resolve_health_event(event_id)
        return {"status": "ok", "resolved": resolved}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@models_router.get("/dashboard/cognitive/repair-proposals")
def get_repair_proposals() -> dict[str, object]:
    """Returns diagnostic self-repair proposals generated during degraded states."""
    try:
        proposals = CognitiveDashboardManager.get_repair_proposals()
        return {"status": "ok", "proposals": proposals}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@models_router.post("/dashboard/cognitive/repair-proposals/{proposal_id}/approve")
def approve_repair_proposal(proposal_id: str) -> dict[str, object]:
    """Approves and executes a diagnostic repair proposal."""
    try:
        success = CognitiveDashboardManager.approve_repair_proposal(proposal_id)
        return {"status": "ok", "success": success}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@models_router.get("/dashboard/cognitive/mral/traces")
def get_mral_traces() -> dict[str, object]:
    """Returns list of reasoning decision traces."""
    try:
        from backend.core.meta_cognition import MRALAuditor
        traces = MRALAuditor.get_all_traces()
        return {"status": "ok", "traces": traces}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@models_router.get("/dashboard/cognitive/mral/traces/{decision_id}")
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


@models_router.post("/dashboard/cognitive/mral/traces/test-run")
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


@models_router.post("/dashboard/cognitive/executive/plans")
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


@models_router.get("/dashboard/cognitive/executive/plans/{blueprint_id}")
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


@models_router.post("/dashboard/cognitive/executive/plans/{blueprint_id}/deploy")
def deploy_executive_plan(blueprint_id: str) -> dict[str, object]:
    """Deploys approved plan to active PPM container."""
    try:
        from backend.core.executive_planner import ExecutivePlanner
        res = ExecutivePlanner.deploy_blueprint_to_ppm(blueprint_id)
        return res
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@models_router.post("/dashboard/cognitive/executive/plans/{project_id}/adapt")
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


@models_router.post("/api/nodes/register/{node_id}")
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



@models_router.get("/api/nodes")
def get_nodes_endpoint() -> dict:
    try:
        from backend.core.node_manager import NodeManager
        nodes = NodeManager.get_nodes()
        return {"status": "ok", "nodes": nodes}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.post("/api/nodes/sweep")
def sweep_nodes_endpoint() -> dict:
    try:
        from backend.core.node_manager import NodeManager
        swept = NodeManager.sweep_nodes()
        return {"status": "ok", "swept_count": swept}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@models_router.websocket("/api/nodes/ws/{node_id}")
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



