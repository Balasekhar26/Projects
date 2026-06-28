from fastapi import APIRouter, WebSocket, Header, HTTPException, Body
from typing import Any
from backend.api.v1.common import *

planner_router = APIRouter(tags=["Planner"])

@planner_router.get("/validators")
def list_validators() -> dict[str, object]:
    from backend.core.validators import DEFAULT_VALIDATORS
    return {"validators": [{"name": v.name, "veto": v.veto} for v in DEFAULT_VALIDATORS.values()]}



@planner_router.post("/validators/run")
def validators_run(request: ValidatorRunRequest) -> dict[str, object]:
    from backend.core.validators import run_validators
    return run_validators(request.payload, request.validators).to_dict()



@planner_router.get("/policy")
def list_policies() -> dict[str, object]:
    from backend.core.execution_policy import DEFAULT_POLICY_ENGINE
    return DEFAULT_POLICY_ENGINE.to_dict()



@planner_router.post("/policy/gate")
def policy_gate(request: PolicyGateRequest) -> dict[str, object]:
    from backend.core.execution_policy import DEFAULT_POLICY_ENGINE
    return DEFAULT_POLICY_ENGINE.gate(
        request.action,
        consensus_approved=request.consensus_approved,
        consensus_requires_human=request.consensus_requires_human,
    ).to_dict()



@planner_router.get("/reliability")
def reliability_stats() -> dict[str, object]:
    from backend.core.reliability_monitor import ReliabilityMonitor
    return ReliabilityMonitor.stats()



@planner_router.post("/reliability/record")
def reliability_record(request: ReliabilityRecordRequest) -> dict[str, object]:
    from backend.core.reliability_monitor import ReliabilityMonitor
    return ReliabilityMonitor.record_outcome(request.agent, request.success)



@planner_router.get("/meta-cognition/status")
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



@planner_router.post("/meta-cognition/supervise")
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



@planner_router.post("/meta-cognition/mode")
def meta_cognition_mode(request: MetaCognitionModeRequest) -> dict[str, object]:
    from backend.core.meta_cognition import MetaCognitionEngine
    return MetaCognitionEngine.select_cognitive_mode(
        prompt=request.prompt,
        is_production=request.is_production,
        is_code_change=request.is_code_change,
    )



@planner_router.get("/executive/status")
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



@planner_router.post("/executive/arbitrate")
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



@planner_router.post("/executive/review")
def post_executive_review(request: ExecutiveReviewRequest) -> dict[str, object]:
    from backend.core.executive_governance import ExecutiveCortex
    return ExecutiveCortex.record_reviewer_decision(
        reviewer_id=request.reviewer_id,
        task_id=request.task_id,
        recommendation=request.recommendation,
        decision=request.decision
    )



@planner_router.post("/cognitive/workflow/save")
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



@planner_router.get("/cognitive/workflow/search")
def cognitive_workflow_search(q: str, limit: int = 10) -> dict[str, object]:
    try:
        results = WorkflowMemory.search_workflows_by_goal(query=q, limit=limit)
        return {"status": "ok", "items": results}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.get("/cognitive/workflow/recent")
def cognitive_workflow_recent(limit: int = 50) -> dict[str, object]:
    try:
        results = WorkflowMemory.get_recent_workflow_runs(limit=limit)
        return {"status": "ok", "items": results}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.post("/cognitive/calibration/record")
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



@planner_router.post("/cognitive/calibration/recalibrate")
def cognitive_calibration_recalibrate() -> dict[str, object]:
    try:
        report = SimulationCalibrator.recalibrate()
        return {"status": "ok", "report": report}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.get("/cognitive/calibration/weights")
def cognitive_calibration_weights() -> dict[str, object]:
    try:
        weights = SimulationCalibrator.get_all_weights()
        return {"status": "ok", "weights": weights}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.post("/cognitive/knowledge-graph/node")
def cognitive_kg_add_node(req: KGNodeRequest) -> dict[str, object]:
    try:
        KnowledgeGraph.add_node(node_id=req.node_id, node_type=req.node_type, properties=req.properties)
        return {"status": "ok", "message": f"Node '{req.node_id}' added successfully."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.post("/cognitive/knowledge-graph/edge")
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



@planner_router.get("/cognitive/knowledge-graph/shortest-path")
def cognitive_kg_shortest_path(source: str, target: str) -> dict[str, object]:
    try:
        path = KnowledgeGraph.find_shortest_path(source_id=source, target_id=target)
        return {"status": "ok", "path": path}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.get("/cognitive/knowledge-graph/subgraph")
def cognitive_kg_subgraph(nodes: str, depth: int = 1) -> dict[str, object]:
    try:
        node_ids = [n.strip() for n in nodes.split(",") if n.strip()]
        subgraph = KnowledgeGraph.get_subgraph(node_ids=node_ids, depth=depth)
        return {"status": "ok", "subgraph": subgraph}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.post("/cognitive/skill-graph/register")
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



@planner_router.get("/cognitive/skill-graph/details/{skill_id}")
def cognitive_skill_details(skill_id: str) -> dict[str, object]:
    try:
        details = SkillGraph.get_skill_details(skill_id=skill_id)
        if not details:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found.")
        return {"status": "ok", "details": details}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.get("/cognitive/skill-graph/dependencies/{skill_id}")
def cognitive_skill_dependencies(skill_id: str) -> dict[str, object]:
    try:
        deps = SkillGraph.get_skill_dependencies(skill_id=skill_id)
        return {"status": "ok", "dependencies": deps}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.post("/cognitive/curriculum/challenge")
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



@planner_router.get("/cognitive/curriculum/challenges")
def cognitive_curriculum_challenges(category: str | None = None, status: str | None = None) -> dict[str, object]:
    try:
        challenges = CurriculumEngine.list_challenges(category=category, status=status)
        return {"status": "ok", "challenges": challenges}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.get("/cognitive/curriculum/recommendations")
def cognitive_curriculum_recommendations() -> dict[str, object]:
    try:
        recs = CurriculumEngine.get_recommended_challenges()
        return {"status": "ok", "recommendations": recs}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.post("/cognitive/project-manager/task")
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



@planner_router.get("/cognitive/project-manager/tasks/{project_name}")
def cognitive_project_tasks(project_name: str) -> dict[str, object]:
    try:
        tasks = ProjectManager.get_project_tasks(project_name=project_name)
        return {"status": "ok", "tasks": tasks}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.post("/cognitive/project-manager/blackboard")
def cognitive_project_blackboard_write(req: BlackboardWriteRequest) -> dict[str, object]:
    try:
        ProjectManager.write_to_blackboard(project_name=req.project_name, key=req.key, value=req.value)
        return {"status": "ok", "message": "Project blackboard updated."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.post("/cognitive/long-term-goals/register")
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



@planner_router.get("/cognitive/long-term-goals/hierarchy")
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


@planner_router.post("/broker/queue")
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



@planner_router.post("/broker/dispatch")
def broker_dispatch(payload: DispatchRequest) -> dict:
    """Dispatch the highest-priority eligible action from the queue.

    Pass ``dry_run=true`` to peek at the next candidate without executing it.
    """
    try:
        from backend.core.action_scheduler import ActionScheduler
        return ActionScheduler.dispatch_next(dry_run=payload.dry_run)
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.get("/broker/queue/snapshot")
def broker_queue_snapshot() -> dict:
    """Return live queue state: pending depth, in-flight, SLA breach summary."""
    try:
        from backend.core.action_scheduler import ActionScheduler
        return ActionScheduler.get_queue_snapshot()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.post("/broker/queue/drain")
def broker_drain_queue() -> dict:
    """Emergency drain: cancel all PENDING and RETRY actions.

    IN_FLIGHT actions are left to complete naturally.
    """
    try:
        from backend.core.action_scheduler import ActionScheduler
        return ActionScheduler.drain_queue()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@planner_router.get("/broker/queue/{queue_id}")
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



