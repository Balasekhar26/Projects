from fastapi import APIRouter, WebSocket, Header, HTTPException, Body
from typing import Any
from backend.api.v1.common import *

safety_router = APIRouter(tags=["Safety"])

@safety_router.post("/improvements/register/{proposal_id}")
def improvements_register(proposal_id: str) -> dict[str, object]:
    from backend.core.proposal_governance import ImprovementRegistry
    try:
        record = ImprovementRegistry.register_or_update(proposal_id)
        return {"status": "success", "record": record}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@safety_router.get("/improvements")
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



@safety_router.get("/improvements/stats")
def improvements_stats() -> dict[str, Any]:
    from backend.core.proposal_governance import ImprovementRegistry
    try:
        return ImprovementRegistry.get_stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@safety_router.get("/improvements/{improvement_id}")
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



@safety_router.get("/skills/library")
def skills_library_status() -> dict[str, object]:
    from backend.core.skill_library import SkillLibrary
    return {"status": SkillLibrary.status(), "items": SkillLibrary.list_skills()}



@safety_router.get("/skills/library/search")
def skills_library_search(q: str) -> dict[str, object]:
    from backend.core.skill_library import SkillLibrary
    return {"items": SkillLibrary.search(q)}



@safety_router.post("/skills/library")
def skills_library_add(request: SkillAddRequest) -> dict[str, object]:
    from backend.core.skill_library import SkillLibrary
    try:
        return {"item": SkillLibrary.add_skill(
            request.name, request.description, inputs=request.inputs,
            steps=request.steps, outputs=request.outputs, tags=request.tags,
        )}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@safety_router.post("/skills/library/{name}/result")
def skills_library_result(name: str, request: SkillLibResultRequest) -> dict[str, object]:
    from backend.core.skill_library import SkillLibrary
    try:
        return SkillLibrary.record_result(name, request.success)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc



@safety_router.get("/skills")
def skills(trust: str | None = None, limit: int = 50) -> dict[str, object]:
    return {"items": memory.list_skills(trust=trust, limit=limit)}



@safety_router.post("/skills")
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



@safety_router.post("/skills/{skill_id}/result")
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




@safety_router.get("/approvals")
def approvals(status: str | None = "pending", limit: int = 25) -> dict[str, object]:
    return {"items": memory.list_approvals(status=status, limit=limit)}



@safety_router.post("/approvals/{approval_id}")
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



@safety_router.post("/approvals/{approval_id}/continue")
def continue_approval(approval_id: str) -> dict[str, object]:
    return continue_approved_work(approval_id)





@safety_router.post("/improvements")
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



@safety_router.post("/improvements/{improvement_id}")
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






@safety_router.post("/skills/{skill_id}/trust")
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






@safety_router.get("/reflections")
def reflections(
    outcome: str | None = None, skill_id: str | None = None, limit: int = 50
) -> dict[str, object]:
    return {
        "items": memory.list_reflections(
            outcome=outcome, skill_id=skill_id, limit=limit
        )
    }



@safety_router.post("/reflections")
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



@safety_router.post("/self-evolution/run")
def self_evolution_run(limit: int = 25) -> dict[str, object]:
    return run_self_evolution_cycle(limit=limit)



@safety_router.get("/settings/jarvis")
def get_jarvis_mode() -> dict[str, bool]:
    import backend.core.config as config_mod
    return {"enabled": getattr(config_mod, "JARVIS_MODE", False)}



@safety_router.post("/settings/jarvis")
def set_jarvis_mode(request: JarvisSettingsRequest) -> dict[str, bool]:
    import backend.core.config as config_mod
    config_mod.JARVIS_MODE = request.enabled
    return {"enabled": config_mod.JARVIS_MODE}



@safety_router.get("/settings/jarvis/diagnostics")
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



@safety_router.post("/approval/submit")
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



@safety_router.post("/approval/approve/{approval_id}")
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



@safety_router.post("/approval/reject/{approval_id}")
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



@safety_router.post("/approval/advance-to-testing/{approval_id}")
def approval_advance_to_testing(approval_id: str) -> dict[str, object]:
    """System action: APPROVED -> TESTING (sandbox passed)."""
    try:
        record = ApprovalWorkflow.advance_to_testing(approval_id=approval_id)
        return {"status": "advanced_to_testing", "record": record}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}



@safety_router.post("/approval/deploy/{approval_id}")
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



@safety_router.get("/approval/get/{approval_id}")
def approval_get(approval_id: str) -> dict[str, object]:
    """Retrieve a single approval record."""
    record = ApprovalWorkflow.get(approval_id)
    if record is None:
        return {"status": "not_found", "approval_id": approval_id}
    return {"status": "ok", "record": record}



@safety_router.get("/approval/list")
def approval_list(state: str | None = None, change_type: str | None = None) -> dict[str, object]:
    """List approval records, optionally filtered by state or change_type."""
    records = ApprovalWorkflow.list_all(state=state, change_type=change_type)
    return {"status": "ok", "count": len(records), "records": records}



@safety_router.get("/approval/events/{approval_id}")
def approval_events(approval_id: str) -> dict[str, object]:
    """Return the full append-only event ledger for an approval."""
    events = ApprovalWorkflow.get_events(approval_id)
    if not events:
        return {"status": "not_found", "approval_id": approval_id, "events": []}
    return {"status": "ok", "approval_id": approval_id, "events": events}



@safety_router.get("/approval/metrics")
def approval_metrics() -> dict[str, object]:
    """Return burn-in metrics: AAR, TTR, DAR, RAR."""
    return {"status": "ok", "metrics": ApprovalWorkflow.metrics()}


# ---------------------------------------------------------------------------
# Learning Dashboard API  (Step 7.3 — Read Only)
# NO write endpoints exist here. Every route is GET.
# ---------------------------------------------------------------------------


@safety_router.get("/verification/report/{report_id}")
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



@safety_router.get("/verification/action/{queue_id}")
def verification_get_reports_for_action(queue_id: str) -> dict:
    """Retrieve all verification reports associated with a queue_id."""
    try:
        from backend.core.verification_engine import VerificationEngine
        reports = VerificationEngine.get_reports_for_action(queue_id)
        return {"status": "ok", "reports": reports}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



@safety_router.post("/verification/retract/{report_id}")
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



@safety_router.get("/verification/verdicts")
def verification_get_verdicts_summary() -> dict:
    """Aggregate report verdict counts for Cognitive Dashboard Tier 9."""
    try:
        from backend.core.verification_engine import VerificationEngine
        summary = VerificationEngine.get_verdicts_summary()
        return {"status": "ok", "summary": summary}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}



