from fastapi.testclient import TestClient

from backend.main import app
from backend.tools.terminal_tools import run_command
from installer import setup_universal_ai


def test_hardware_requirements_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/system/hardware-requirements")
    assert response.status_code == 200
    data = response.json()
    assert {tier["tier"] for tier in data["tiers"]} == {
        "minimum",
        "recommended",
        "full_potential",
        "maximum",
    }
    assert "configured_models" in data
    assert "ram_total_gb" in data["system"]
    assert "buying_guide" in data
    assert {item["tier"] for item in data["buying_guide"]} == {
        "minimum",
        "recommended",
        "full_potential",
        "maximum_lab",
    }
    assert "desktop-first" in data["recommendation"]


def test_platform_support_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/system/platform-support")
    assert response.status_code == 200
    data = response.json()
    features = {item["feature"]: item for item in data["features"]}
    assert data["os"]["system"]
    assert "desktop_control" in features
    assert "speech_output" in features
    assert "local_file_transfer" in features
    assert features["local_file_transfer"]["adapter"] == "LocalSend optional adapter"
    assert "Windows, macOS, and Linux" in data["promise"]


def test_cluster_plan_is_consent_based_and_capability_aware() -> None:
    client = TestClient(app)
    response = client.get("/cluster/plan")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "consent_based_local_cluster"
    assert data["can_run_as_one_system"] == "planned_not_enabled"
    assert data["pairing_policy"]["installation_agreement_disclosure_required"] is True
    assert data["pairing_policy"]["explicit_user_consent_required"] is True
    assert data["pairing_policy"]["no_hidden_install_or_silent_join"] is True
    assert data["pairing_policy"]["remote_actions_need_approval"] is True
    assert data["auto_connect_policy"]["enabled_after_explicit_pairing"] is True
    assert data["auto_connect_policy"]["multiple_active_paired_nodes"] is True
    assert "paired_high_spec_node_is_online" in data["auto_connect_policy"]["connect_when"]
    assert "model_inference" in data["auto_connect_policy"]["run_without_extra_prompt"]
    assert "assigned_work_is_complete" in data["auto_connect_policy"]["disconnect_when"]
    assert data["improvement_sync_policy"]["auto_share_with_paired_nodes"] is True
    assert data["improvement_sync_policy"]["auto_apply_on_receiving_nodes"] is False
    assert "approved_skills" in data["improvement_sync_policy"]["shared_data"]
    assert "raw_user_chat_history" in data["improvement_sync_policy"]["never_auto_share"]
    assert "request_local_user_or_manager_approval" in data["improvement_sync_policy"]["receiving_node_flow"]
    assert data["improvement_sync_policy"]["canonical_distribution"] == "git_repo"
    assert "write_proposal_to_git_repo_registry" in data["improvement_sync_policy"]["publish_flow"]
    repo_distribution = data["improvement_sync_policy"]["git_repo_distribution"]
    assert repo_distribution["enabled"] is True
    assert repo_distribution["path"] == "docs/SHARED_IMPROVEMENTS.md"
    assert repo_distribution["applies_to"] == "paired_and_unpaired_systems"
    assert repo_distribution["direct_push_to_other_systems"] is False
    assert repo_distribution["unpaired_check_policy"]["enabled"] is True
    assert repo_distribution["unpaired_check_policy"]["default_interval_hours"] == 24
    assert repo_distribution["unpaired_check_policy"]["if_new_data_found"] == "request_local_user_or_manager_approval"
    assert repo_distribution["paired_check_policy"]["enabled"] is True
    assert repo_distribution["paired_check_policy"]["default_interval_hours"] == 24
    assert data["capability_policy"]["no_unlimited_node"] is True
    assert data["capability_policy"]["manager_must_check_capability_before_assignment"] is True
    assert data["capability_policy"]["worker_must_reject_over_limit_tasks"] is True
    assert data["approval_policy"]["ordinary_cluster_routing_approval"] == "installation_agreement"
    assert data["approval_policy"]["ordinary_cluster_routing_runtime_prompt"] is False
    assert "shell_commands" in data["approval_policy"]["runtime_approval_required_for"]
    assert "capability_tier" in data["node"]
    assert "local_tasks" in data
    assert "delegate_when_needed" in data
    assert data["storage_policy"]["source_of_truth"] == "manager_node"
    assert data["storage_policy"]["chat_history_location"] == "task_origin_main_system"
    assert data["storage_policy"]["only_durable_cross_system_shared_data"] == "approved_sanitized_improvement_data"
    assert data["storage_policy"]["worker_persistent_chat_storage"] is False
    assert data["storage_policy"]["worker_persistent_task_storage"] is False
    assert data["storage_policy"]["worker_task_context_delete_after_completion"] is True
    assert data["storage_policy"]["worker_task_context_delete_on_failure_or_cancel"] is True
    assert data["storage_policy"]["worker_result_flow"] == "return_result_to_manager_then_discard_task_context"
    assert data["workspace_policy"]["shared_workspace"] is True
    assert data["workspace_policy"]["shared_workspace_is_not_shared_private_data"] is True
    assert data["workspace_policy"]["durable_shared_workspace_data"] == "approved_sanitized_improvement_data_only"
    assert "approved_sanitized_improvement_proposals" in data["workspace_policy"]["shared_items"]
    assert "project_task_payloads" in data["workspace_policy"]["not_shared_as_workspace_data"]
    assert "raw_chat_history" in data["workspace_policy"]["not_shared_as_workspace_data"]
    assert data["free_cluster_tools"]["inference"] == "exo_local_ai_cluster"
    assert data["free_cluster_tools"]["workers"] == "ray_local_cluster"


def test_installation_agreement_mentions_cluster_consent() -> None:
    text = setup_universal_ai.INSTALLATION_AGREEMENT.read_text(encoding="utf-8")
    assert "Multi-system cluster mode" in text
    assert "explicit pairing/approval" in text
    assert "must not silently join" in text
    assert "automatically reconnect to that paired system" in text
    assert "stored on the task-origin main/manager system" in text
    assert "only durable cross-system shared data" in text
    assert "delete task context after completion, failure, or cancellation" in text
    assert "This shared workspace is not shared private data" in text
    assert "no node is treated as unlimited" in text
    assert "ordinary cluster participation and task routing" in text
    assert "multiple already-paired systems at the same time" in text
    assert "published to the Universal AI Git repository" in text
    assert "paired or unpaired" in text
    assert "should not directly push improvement data to other systems" in text
    assert "default interval of 24 hours" in text
    assert "Raw user chat history" in text


def test_shared_improvements_registry_blocks_private_data() -> None:
    registry = setup_universal_ai.ROOT / "docs" / "SHARED_IMPROVEMENTS.md"
    text = registry.read_text(encoding="utf-8")
    assert "Git-repo distribution point" in text
    assert "paired or unpaired" in text
    assert "any system may publish approved, sanitized improvement proposals" in text
    assert "Default check interval: once every 24 hours" in text
    assert "must not directly push improvement data to other systems" in text
    assert "raw user chat history" in text
    assert "credentials, tokens, keys, or secrets" in text


def test_installer_writes_cluster_safety_defaults(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(setup_universal_ai, "BACKEND_ENV", env_path)
    profile = setup_universal_ai.MachineProfile(
        tier="minimum",
        cpu_logical=4,
        ram_gb=8.0,
        fast="qwen2.5:0.5b",
        general="phi3:latest",
        coder="qwen2.5-coder:3b",
        power="qwen3:4b",
        vision="disabled",
        reasoning="disabled",
        whisper="base",
    )
    setup_universal_ai.write_backend_env(profile)
    text = env_path.read_text(encoding="utf-8")
    assert "SEKHAR_CLUSTER_ENABLED=false" in text
    assert "SEKHAR_CLUSTER_PAIRING_REQUIRED=true" in text
    assert "SEKHAR_REMOTE_ACTIONS_NEED_APPROVAL=true" in text
    assert "SEKHAR_UNPAIRED_IMPROVEMENT_CHECK_ENABLED=true" in text
    assert "SEKHAR_UNPAIRED_IMPROVEMENT_CHECK_INTERVAL_HOURS=24" in text
    assert "SEKHAR_PAIRED_IMPROVEMENT_CHECK_ENABLED=true" in text
    assert "SEKHAR_PAIRED_IMPROVEMENT_CHECK_INTERVAL_HOURS=24" in text
    assert "SEKHAR_SHARED_IMPROVEMENT_REPO_PATH=docs/SHARED_IMPROVEMENTS.md" in text
    assert "SEKHAR_SHARED_IMPROVEMENT_AUTO_APPLY=false" in text


def test_terminal_safe_prefix_cannot_smuggle_shell_control() -> None:
    result = run_command("git status; echo unsafe")
    assert result["approval_required"] is True


def test_terminal_safe_exact_command_still_runs() -> None:
    result = run_command("git status")
    assert result["returncode"] == 0
    assert "stdout" in result
