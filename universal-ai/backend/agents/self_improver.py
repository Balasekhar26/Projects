from __future__ import annotations

from backend.core.memory import memory, remember
from backend.core.model_router import ask_model


def self_improver_node(state):
    user_request = state["user_input"]
    proposal = ask_model(
        f"Self-improvement request: {user_request}\n"
        "Propose a safe improvement. Include reason, files, tests, risk, rollback. "
        "Do not change safety rules or files silently.",
        role="coder",
    )
    remember(proposal, category="self_improvement_memory")
    improvement_id = memory.create_improvement(
        title="Self-improvement proposal",
        motive=user_request,
        proposal=proposal,
        risk="medium",
    )
    skill_id = memory.create_skill(
        name="Review Self-Improvement Proposal",
        trigger=user_request[:120],
        steps=(
            "1. Read the proposal and compare it to Bala's original motive.\n"
            "2. Check safety, local/free-only constraints, files, tests, and rollback plan.\n"
            "3. Ask for approval before applying any code or configuration change.\n"
            "4. After execution, record a reflection and evaluation."
        ),
        tools="memory, tests, local model, approved filesystem tools",
        risk="medium",
        trust="draft",
        last_reflection=proposal[:500],
    )
    memory.create_skill_evaluation(
        skill_id=skill_id,
        result="needs_review",
        score=50,
        notes="Draft skill created from self-improvement request. Requires human approval.",
    )
    approval_id = memory.create_approval(
        action=f"Review self-improvement proposal {improvement_id} and draft skill {skill_id}: {user_request}",
        risk="medium",
    )
    state["approval_id"] = approval_id
    state["approval_required"] = True
    state["result"] = (
        "Self-improvement proposal saved. Approval required before applying changes.\n"
        f"Improvement id: {improvement_id}\n"
        f"Draft skill id: {skill_id}\n"
        f"Approval id: {approval_id}\n\n"
        + proposal
    )
    state["logs"].append("self_improver: backlog proposal and approval generated")
    return state
