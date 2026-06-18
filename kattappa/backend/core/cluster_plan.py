from __future__ import annotations

import platform
import socket
from typing import Any


TASK_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "desktop_ui": {"min_ram_gb": 4, "min_cpu_logical": 2, "delegable": False},
    "basic_chat": {"min_ram_gb": 8, "min_cpu_logical": 4, "delegable": True},
    "project_memory": {"min_ram_gb": 8, "min_cpu_logical": 4, "delegable": True},
    "repo_indexing": {"min_ram_gb": 16, "min_cpu_logical": 6, "delegable": True},
    "voice_transcription": {"min_ram_gb": 16, "min_cpu_logical": 6, "delegable": True},
    "screen_ocr": {"min_ram_gb": 16, "min_cpu_logical": 6, "delegable": False},
    "small_local_model": {"min_ram_gb": 16, "min_cpu_logical": 6, "delegable": True},
    "large_local_model": {"min_ram_gb": 64, "min_cpu_logical": 12, "delegable": True},
    "simulation": {"min_ram_gb": 16, "min_cpu_logical": 6, "delegable": True},
    "physical_ai_lab": {"min_ram_gb": 64, "min_cpu_logical": 12, "delegable": True},
}


def cluster_plan() -> dict[str, Any]:
    profile = local_node_profile()
    runnable = _runnable_tasks(profile)
    delegated = _delegation_plan(profile, runnable)
    return {
        "mode": "consent_based_local_cluster",
        "can_run_as_one_system": "enabled_for_paired_nodes_and_unpaired_discovery_workers",
        "runtime_status": "local_http_worker_handoff_enabled",
        "broker_status": "paired_and_unpaired_capability_bid_broadcast_enabled",
        "node": profile,
        "local_tasks": runnable,
        "delegate_when_needed": delegated,
        "routing_rule": (
            "Run work on the local machine only when it fits local CPU/RAM/capability limits. "
            "For heavier work, ask paired workers and unpaired discovery workers for a capability bid, "
            "then delegate only to the strongest safe reply. "
            "Even strong nodes have hard limits and must run only tasks inside their measured capability profile."
        ),
        "capability_policy": {
            "weak_nodes": "run_only_light_tasks_within_measured_cpu_ram_permissions",
            "strong_nodes": "run_heavier_tasks_but_never_beyond_measured_cpu_ram_gpu_permissions",
            "no_unlimited_node": True,
            "manager_must_check_capability_before_assignment": True,
            "worker_must_reject_over_limit_tasks": True,
            "task_requirements": TASK_REQUIREMENTS,
        },
        "pairing_policy": {
            "installation_agreement_disclosure_required": True,
            "automatic_after_pairing": True,
            "unpaired_discovery_supported": True,
            "unpaired_bid_contains_task_content": False,
            "unpaired_assignment_requires_one_time_task_token": True,
            "explicit_user_consent_required": True,
            "no_hidden_install_or_silent_join": True,
            "trusted_network_only": True,
            "public_internet_nodes_require_https_and_pairing_token": True,
            "public_unpaired_discovery_targets_require_https": True,
            "remote_actions_need_approval": True,
        },
        "auto_connect_policy": {
            "enabled_after_explicit_pairing": True,
            "enabled_for_unpaired_discovery_targets": True,
            "multiple_active_paired_nodes": True,
            "capability_bid_broadcast": True,
            "worker_selection": "highest_capability_bid_with_cleanup_receipt_required",
            "max_active_nodes": "bounded_by_manager_capacity_and_network_health",
            "connect_when": [
                "manager_has_task_that_exceeds_local_capability",
                "paired_opened_internet_connected_node_replies_to_bid",
                "unpaired_opened_internet_connected_kattappa_worker_replies_to_safe_bid",
                "task_fits_remote_node_capability_policy",
            ],
            "run_without_extra_prompt": [
                "non_sensitive_worker_jobs",
                "model_inference",
                "repo_indexing",
                "tests",
                "simulation",
                "read_only_analysis",
            ],
            "disconnect_when": [
                "assigned_work_is_complete",
                "node_is_idle_past_timeout",
                "manager_or_worker_requests_disconnect",
                "network_is_untrusted_or_unhealthy",
            ],
            "worker_process_lifecycle": (
                "Receive a bid request, reply with capability only, accept the assigned job only if selected, "
                "run the capability-checked job, return progress/results to the manager, delete task payload "
                "context, then stop, idle, or disconnect according to policy."
            ),
        },
        "improvement_sync_policy": {
            "auto_share_with_paired_nodes": False,
            "auto_apply_on_receiving_nodes": False,
            "canonical_distribution": "local_project_registry",
            "sync_after": [
                "approved_self_improvement",
                "trusted_skill_update",
                "tool_policy_update",
                "capability_profile_update",
                "test_result_summary",
                "safe_reflection_summary",
            ],
            "shared_data": [
                "approved_skills",
                "trusted_tool_rules",
                "free_tool_replacements",
                "cluster_capability_profiles",
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
            "publish_flow": [
                "system_generates_improvement",
                "local_user_or_manager_approves_improvement",
                "sanitize_shared_improvement_payload",
                "write_proposal_to_local_project_registry",
            ],
            "sync_direction": "each_system_publishes_to_git_repo_and_all_systems_pull_from_git_repo",
            "git_repo_distribution": {
                "enabled": True,
                "path": "docs/IMPROVEMENT_REGISTRY.md",
                "applies_to": "local_kattappa_project_only",
                "share_with_all_systems": "disabled",
                "direct_push_to_other_systems": False,
                "publish_to_configured_git_remote": "allowed_for_approved_sanitized_improvement_proposals",
                "export_format": "approved_sanitized_improvement_proposals",
                "unpaired_check_policy": {
                    "enabled": False,
                    "default_interval_hours": 24,
                    "check_jitter_minutes": 30,
                    "manual_check_supported": True,
                    "network_required": True,
                    "check_action": "read_local_improvement_registry",
                    "if_new_data_found": "request_local_user_or_manager_approval",
                    "if_no_approval": "store_as_pending_proposal_only",
                    "adopt_after": "local_approval_and_compatibility_checks",
                },
                "paired_check_policy": {
                    "enabled": False,
                    "default_interval_hours": 24,
                    "check_jitter_minutes": 30,
                    "manual_check_supported": True,
                    "check_action": "read_local_improvement_registry",
                    "if_new_data_found": "request_local_user_or_manager_approval",
                    "if_no_approval": "store_as_pending_proposal_only",
                    "adopt_after": "local_approval_and_compatibility_checks",
                },
                "receiving_unpaired_system_flow": [
                    "wait_until_next_scheduled_check_or_manual_check",
                    "read_local_improvement_registry",
                    "read_local_improvement_proposal",
                    "verify_free_tool_policy_and_safety_scope",
                    "run_local_compatibility_checks",
                    "request_local_user_or_manager_approval",
                    "adopt_only_after_local_approval",
                ],
                "receiving_paired_system_flow": [
                    "wait_until_next_scheduled_check_or_manual_check",
                    "read_local_improvement_registry",
                    "read_local_improvement_proposal",
                    "verify_free_tool_policy_and_safety_scope",
                    "run_local_compatibility_checks",
                    "request_local_user_or_manager_approval",
                    "adopt_only_after_local_approval",
                ],
            },
            "receiving_node_flow": [
                "read_improvement_proposal_from_local_registry",
                "verify_origin_metadata_and_signature_if_present",
                "check_free_tool_policy_and_safety_scope",
                "run_local_compatibility_checks",
                "request_local_user_or_manager_approval",
                "adopt_only_after_local_approval",
            ],
            "conflict_rule": (
                "An improvement approved on this project stays local by default. Local approval is required "
                "before Kattappa activates the skill, tool rule, or behavior."
            ),
        },
        "approval_policy": {
            "ordinary_cluster_routing_approval": "installation_agreement",
            "ordinary_cluster_routing_runtime_prompt": False,
            "pairing_approval": "explicit_device_pairing_after_install",
            "runtime_approval_required_for": [
                "shell_commands",
                "file_writes",
                "installs_or_downloads",
                "desktop_control",
                "credential_or_secret_access",
                "destructive_actions",
                "sensitive_data_transfer",
            ],
        },
        "storage_policy": {
            "source_of_truth": "manager_node",
            "chat_history_location": "task_origin_main_system",
            "task_history_location": "task_origin_main_system",
            "approval_history_location": "task_origin_main_system",
            "only_durable_cross_system_shared_data": "none_by_default",
            "worker_persistent_chat_storage": False,
            "worker_persistent_task_storage": False,
            "worker_context_retention": "temporary_for_task_only",
            "worker_result_flow": "return_result_to_manager_then_discard_task_context",
            "worker_task_context_delete_after_completion": True,
            "worker_task_context_delete_on_failure_or_cancel": True,
            "worker_task_context_delete_verification": "best_effort_delete_then_report_to_manager",
            "manager_write_rule": (
                "Only the task-origin manager node writes chat, task, approval, and long-term memory. "
                "Worker nodes may keep operational logs, but not user chat/task history or task-private context."
            ),
        },
        "workspace_policy": {
            "shared_workspace": False,
            "shared_workspace_is_not_shared_private_data": True,
            "durable_shared_workspace_data": "none_by_default",
            "workspace_source": "local_project_index",
            "shared_items": [
                "approved_local_improvement_registry",
                "approved_sanitized_local_improvement_proposals",
            ],
            "not_shared_as_workspace_data": [
                "project_task_payloads",
                "temporary_worker_task_context",
                "raw_chat_history",
                "private_task_context",
                "approval_private_notes",
                "credentials_or_secrets",
                "sensitive_local_files",
                "machine_private_memory",
            ],
            "worker_workspace_flow": [
                "open_local_project",
                "read_project_index_and_task_context_from_manager",
                "work_only_on_assigned_files_or_tasks",
                "return_patch_result_or_artifact_to_manager",
                "delete_task_context_after_completion_failure_or_cancel",
                "do_not_persist_private_chat_task_memory_or_task_payloads",
            ],
        },
        "free_cluster_tools": {
            "inference": "exo_local_ai_cluster",
            "workers": "ray_local_cluster",
            "current_runtime": "built_in_kattappa_local_http_worker_runtime",
        },
        "next_build_steps": [
            "Add signed pairing tokens for trusted devices.",
            "Persist approved nodes with hostname, fingerprint, and capability profile.",
            "Use Ray for approved worker jobs: indexing, tests, simulation, and scans.",
            "Use exo later for approved multi-machine local model inference.",
            "Auto-connect to already paired high-spec nodes only when a task needs them.",
            "Allow multiple paired workers to be active at the same time when tasks and capacity require it.",
            "Auto-disconnect or idle paired workers after assigned work completes.",
            "Store approved sanitized self-improvement data in the local project registry.",
            "Keep chat, task, approval, and long-term memory on the task-origin manager node.",
            "Make worker nodes return results and discard task context after completion.",
        ],
    }


def local_node_profile() -> dict[str, Any]:
    cpu_logical: int | None = None
    cpu_physical: int | None = None
    ram_total_gb: float | None = None
    try:
        import psutil

        cpu_logical = psutil.cpu_count(logical=True)
        cpu_physical = psutil.cpu_count(logical=False)
        ram_total_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception:
        pass

    profile = {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpu_count_logical": cpu_logical,
        "cpu_count_physical": cpu_physical,
        "ram_total_gb": ram_total_gb,
    }
    profile["capability_tier"] = _capability_tier(cpu_logical, ram_total_gb)
    return profile


def _capability_tier(cpu_logical: int | None, ram_total_gb: float | None) -> str:
    cpu = cpu_logical or 0
    ram = ram_total_gb or 0
    if cpu >= 12 and ram >= 64:
        return "heavy_worker"
    if cpu >= 6 and ram >= 16:
        return "standard_worker"
    if cpu >= 4 and ram >= 8:
        return "light_worker"
    return "controller_only"


def _runnable_tasks(profile: dict[str, Any]) -> list[str]:
    cpu = int(profile.get("cpu_count_logical") or 0)
    ram = float(profile.get("ram_total_gb") or 0)
    return [
        task
        for task, requirement in TASK_REQUIREMENTS.items()
        if cpu >= requirement["min_cpu_logical"] and ram >= requirement["min_ram_gb"]
    ]


def _delegation_plan(profile: dict[str, Any], runnable: list[str]) -> list[dict[str, str]]:
    runnable_set = set(runnable)
    delegated: list[dict[str, str]] = []
    for task, requirement in TASK_REQUIREMENTS.items():
        if task in runnable_set or not requirement["delegable"]:
            continue
        delegated.append(
            {
                "task": task,
                "target": "approved_peer_node",
                "reason": (
                    f"Needs at least {requirement['min_cpu_logical']} logical CPU and "
                    f"{requirement['min_ram_gb']} GB RAM; local tier is {profile['capability_tier']}."
                ),
            }
        )
    return delegated
