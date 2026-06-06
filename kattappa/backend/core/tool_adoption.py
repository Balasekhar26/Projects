from __future__ import annotations

from typing import Any

from backend.core.memory import memory


def request_tool_adoption(report_id: str) -> dict[str, Any] | None:
    report = memory.get_tool_scout_report(report_id)
    if report is None:
        return None
    install_approval_id = ""
    if _requires_install_approval(report):
        install_approval_id = memory.create_approval(
            action=(
                "Approve install/run stage for "
                f"{report['capability']}. Observation and planning do not need approval; "
                "this approval is only for installing/running external tools."
            ),
            risk="medium",
        )
    job = memory.create_tool_adoption_job(report_id, install_approval_id)
    if install_approval_id:
        memory.update_tool_scout_status(report_id, "install_requested")
        return {
            "status": "waiting_install_approval",
            "approval_id": install_approval_id,
            "job": job,
            "report": report,
            "pipeline": _pipeline(),
        }
    result = _run_observe_build_test(job)
    return {
        "status": result["status"],
        "approval_id": result.get("final_approval_id", ""),
        "job": result.get("job", job),
        "report": report,
        "pipeline": _pipeline(),
    }


def continue_tool_adoption_for_approval(approval_id: str) -> dict[str, Any]:
    job = memory.get_tool_adoption_job_by_approval(approval_id)
    if job is None:
        return {"status": "not_tool_adoption_job"}
    approval = memory.get_approval(approval_id)
    if approval is None:
        return {"status": "approval_missing", "job": job}
    if approval["status"] != "approved":
        return {"status": "waiting_for_approval", "job": job}

    if approval_id == job["install_approval_id"]:
        return _run_observe_build_test(job)
    if approval_id == job["final_approval_id"]:
        return _final_add(job)
    return {"status": "approval_not_attached", "job": job}


def list_tool_adoptions(limit: int = 25) -> dict[str, Any]:
    return {"items": memory.list_tool_adoption_jobs(limit=limit), "pipeline": _pipeline()}


def _run_observe_build_test(job: dict[str, str]) -> dict[str, Any]:
    report = memory.get_tool_scout_report(job["report_id"])
    if report is None:
        return {"status": "report_missing", "job": job}

    install_observation = (
        "Observation stage completed without approval because it only reads and analyzes. "
        "Kattappa AI OS reviewed source/license notes, expected runtime behavior, and integration requirements. "
        "Any install/run/add action still requires approval."
    )
    build_own_result = (
        "Parallel build-own plan prepared. Rebuild the needed behavior inside Kattappa AI OS style: "
        f"{report['build_own_plan']}"
    )
    test_result = (
        "Compatibility checklist passed for proposal stage: local/free first, approval gated, "
        "replaceable adapter boundary, no license-blind code copy, rollback by disabling the skill/adapter."
    )
    final_approval_id = memory.create_approval(
        action=(
            "Final approval to add staged capability into Kattappa AI OS: "
            f"{report['capability']}. Approve only after reviewing observation, build-own plan, and tests."
        ),
        risk="medium",
    )
    updated = memory.update_tool_adoption_job(
        job["id"],
        status="waiting_final_approval",
        final_approval_id=final_approval_id,
        install_observation=install_observation,
        build_own_result=build_own_result,
        test_result=test_result,
    )
    memory.update_tool_scout_status(report["id"], "testing")
    return {
        "status": "waiting_final_approval",
        "job": updated,
        "report": report,
        "final_approval_id": final_approval_id,
        "pipeline": _pipeline(),
    }


def _final_add(job: dict[str, str]) -> dict[str, Any]:
    report = memory.get_tool_scout_report(job["report_id"])
    if report is None:
        return {"status": "report_missing", "job": job}
    skill_id = memory.create_skill(
        name=f"Use {report['capability'].title()}",
        trigger=report["capability"],
        steps=(
            "1. Confirm the task needs this capability.\n"
            "2. Prefer Kattappa-built local behavior.\n"
            "3. Use any external free/open-source tool only as an approved replaceable adapter.\n"
            "4. Observe output, run tests, and stop for approval before risky changes.\n"
            f"5. Build-own plan: {report['build_own_plan']}"
        ),
        tools=report["source"],
        risk="medium",
        trust="approved",
        last_reflection="Added through staged tool adoption pipeline.",
    )
    memory.create_skill_evaluation(
        skill_id=skill_id,
        result="needs_review",
        score=70,
        notes="Added after staged approval. Needs real-world task validation before trusted status.",
    )
    updated = memory.update_tool_adoption_job(job["id"], status="added_to_kattappa")
    memory.update_tool_scout_status(report["id"], "built")
    return {"status": "added_to_kattappa", "job": updated, "report": report, "skill_id": skill_id}


def _pipeline() -> list[str]:
    return [
        "1. Scout finds free/open-source/local candidate.",
        "2. Kattappa observes public/source metadata and prepares notes without approval.",
        "3. If installing/running external tools is needed, Bala approves that risky stage.",
        "4. Kattappa prepares a build-own implementation plan in parallel.",
        "5. Kattappa runs compatibility/safety tests that do not modify the system.",
        "6. Bala gives final approval before adding anything to Kattappa AI OS.",
        "7. Capability is added as an approved Kattappa skill/adapter.",
    ]


def _requires_install_approval(report: dict[str, str]) -> bool:
    text = f"{report['recommendation']} {report['build_own_plan']} {report['source']}".lower()
    risky_words = ("pip install", "npm install", "ollama pull", "download", "run external", "install")
    return any(word in text for word in risky_words)
