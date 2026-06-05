from __future__ import annotations

from collections import Counter
from typing import Any

from backend.core.memory import memory


def run_self_evolution_cycle(limit: int = 25) -> dict[str, Any]:
    reflections = memory.list_reflections(limit=limit)
    failure_like = [item for item in reflections if item["outcome"] in {"failure", "partial"}]
    existing_triggers = {str(skill["trigger"]).lower() for skill in memory.list_skills(limit=200)}

    created: list[dict[str, object]] = []
    for item in failure_like[:5]:
        trigger = _normalize_trigger(str(item["task"]))
        if trigger.lower() in existing_triggers:
            continue
        skill_id = memory.create_skill(
            name=_skill_name(trigger),
            trigger=trigger,
            steps=_draft_steps(str(item["lesson"])),
            tools="local model, memory, approved tools",
            risk="medium",
            trust="draft",
            last_reflection=str(item["lesson"]),
        )
        memory.create_skill_evaluation(
            skill_id=skill_id,
            result="needs_review",
            score=50,
            notes="Draft skill created from reflection. Requires Bala approval and real task validation.",
        )
        approval_id = memory.create_approval(
            action=f"Review and approve draft self-evolution skill {skill_id}: {trigger}",
            risk="medium",
        )
        created.append({"skill_id": skill_id, "approval_id": approval_id, "trigger": trigger})
        existing_triggers.add(trigger.lower())

    return {
        "cycle": "read_execute_reflect_write",
        "fully_free_only": True,
        "cluster_sync": improvement_sync_manifest(),
        "reflections_scanned": len(reflections),
        "failure_patterns": _patterns(failure_like),
        "draft_skills_created": created,
        "next_step": (
            "Approve useful draft skills, then run them on real tasks and record success/failure."
            if created
            else "No new draft skills needed. Add reflections after real tasks to keep learning."
        ),
    }


def improvement_sync_manifest() -> dict[str, Any]:
    return {
        "auto_share_with_paired_nodes": True,
        "auto_apply_on_receiving_nodes": False,
        "canonical_distribution": "git_repo",
        "share_only_after": ["approval", "trusted_skill_update", "sanitization"],
        "publish_flow": [
            "local_approval",
            "sanitize_payload",
            "write_to_docs_shared_improvements",
            "commit_or_stage_for_push",
        ],
        "receiving_node_flow": [
            "fetch_from_git_repo_as_proposal",
            "verify_origin_metadata_and_signature_if_present",
            "check_local_policy_and_compatibility",
            "ask_local_approval",
            "adopt_after_local_approval",
        ],
        "git_repo_distribution": {
            "enabled": True,
            "path": "docs/SHARED_IMPROVEMENTS.md",
            "applies_to": "paired_and_unpaired_systems",
            "share_with_all_systems": "via_git_clone_fetch_or_pull",
            "direct_push_to_other_systems": False,
            "publish_to_configured_git_remote": "allowed_for_approved_sanitized_improvement_proposals",
            "unpaired_check_policy": {
                "enabled": True,
                "default_interval_hours": 24,
                "manual_check_supported": True,
                "if_new_data_found": "ask_local_approval",
                "if_no_approval": "store_as_pending_proposal_only",
            },
            "paired_check_policy": {
                "enabled": True,
                "default_interval_hours": 24,
                "manual_check_supported": True,
                "if_new_data_found": "ask_local_approval",
                "if_no_approval": "store_as_pending_proposal_only",
            },
            "receiving_unpaired_system_flow": [
                "scheduled_or_manual_git_update_check",
                "pull_or_clone_git_repo",
                "verify_shared_improvement",
                "ask_local_approval",
                "adopt_after_local_approval",
            ],
            "receiving_paired_system_flow": [
                "scheduled_or_manual_git_update_check",
                "fetch_or_pull_git_repo",
                "verify_shared_improvement",
                "ask_local_approval",
                "adopt_after_local_approval",
            ],
        },
        "shared_data": [
            "approved_skills",
            "trusted_tool_rules",
            "free_tool_replacements",
            "capability_profiles",
            "sanitized_reflection_lessons",
            "test_and_validation_summaries",
        ],
        "never_auto_share": [
            "raw_user_chat_history",
            "task_private_context",
            "approval_private_notes",
            "credentials_or_secrets",
            "sensitive_files",
        ],
        "conflict_rule": "origin_approval_allows_git_publication; receiving_node_approval_allows_activation",
    }


def _normalize_trigger(task: str) -> str:
    cleaned = " ".join(task.strip().split())
    return cleaned[:120] if cleaned else "general repeated task"


def _skill_name(trigger: str) -> str:
    words = [word for word in trigger.replace("_", " ").split() if word]
    title = " ".join(words[:6]).title()
    return f"Handle {title}" if title else "Handle Repeated Task"


def _draft_steps(lesson: str) -> str:
    return "\n".join(
        [
            "1. Read the user goal and retrieve related memories/reflections.",
            "2. Check whether this skill applies to the current task.",
            f"3. Apply the learned lesson: {lesson[:500]}",
            "4. Use only configured free/local tools.",
            "5. Stop for approval before file writes, installs, desktop actions, or risky commands.",
            "6. Record a reflection with the outcome so the skill can improve again.",
        ]
    )


def _patterns(reflections: list[dict[str, str | None]]) -> list[dict[str, object]]:
    counter = Counter(_normalize_trigger(str(item["task"])).lower() for item in reflections)
    return [{"trigger": key, "count": count} for key, count in counter.most_common(5)]
