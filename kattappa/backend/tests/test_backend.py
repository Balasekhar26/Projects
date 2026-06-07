from fastapi.testclient import TestClient

from backend.agents.planner import route_task
from backend.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Kattappa AI OS backend running"
    assert "memory_count" in data


def test_voice_backend_pipeline_endpoints() -> None:
    client = TestClient(app)
    status_response = client.get("/voice/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["mode"] == "local_backend_voice_pipeline"
    assert status["browser_speech_primary"] is False
    assert status["wake"]["engine"] == "openwakeword"
    assert status["wake"]["primary_decision"] in {"openwakeword_custom_models", "local_stt_wake_name_parser"}
    assert status["profile"]["primary_spoken_language"] == "Telugu"
    assert status["profile"]["text_output_language"] == "English"

    parse_response = client.post("/voice/parse-wake", json={"transcript": "Mama check status"})
    assert parse_response.status_code == 200
    parsed = parse_response.json()
    assert parsed["wake_detected"] is True
    assert parsed["wake_name"] == "mama"
    assert parsed["command"] == "check status"


def test_approval_lifecycle() -> None:
    client = TestClient(app)
    chat_response = client.post("/chat", json={"message": "delete temp files after showing me the plan"})
    assert chat_response.status_code == 200
    state = chat_response.json()["state"]
    approval_id = state["approval_id"]
    assert state["approval_required"] is True
    assert approval_id

    pending_response = client.get("/approvals", params={"status": "pending", "limit": 5})
    assert pending_response.status_code == 200
    pending_ids = {item["id"] for item in pending_response.json()["items"]}
    assert approval_id in pending_ids

    decision_response = client.post(f"/approvals/{approval_id}", json={"status": "rejected"})
    assert decision_response.status_code == 200
    assert decision_response.json()["item"]["status"] == "rejected"


def test_operator_plan_endpoint() -> None:
    client = TestClient(app)
    response = client.post("/operator/plan", json={"message": "guide me with cursor to open settings"})
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["mode"] == "guide"
    assert plan["local_only"] is True
    assert "next_steps" in plan


def test_operator_plan_honors_explicit_mode() -> None:
    client = TestClient(app)
    response = client.post("/operator/plan", json={"message": "[operator mode: autonomous]\nopen settings"})
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["mode"] == "autonomous"
    assert plan["needs_approval"] is True


def test_chat_returns_operator_plan() -> None:
    client = TestClient(app)
    response = client.post("/chat", json={"message": "guide me with cursor to inspect the screen"})
    assert response.status_code == 200
    state = response.json()["state"]
    assert state["operator_plan"]["mode"] == "guide"
    assert state["operator_plan"]["local_only"] is True


def test_embedded_systems_uses_built_in_local_answer() -> None:
    client = TestClient(app)
    response = client.post("/chat", json={"message": "explain embedded systems"})
    assert response.status_code == 200
    data = response.json()
    assert data["state"]["selected_agent"] == "coder"
    assert "dedicated computer inside a device" in data["response"]
    assert any("built-in local knowledge" in line for line in data["state"]["logs"])
    assert any("tool_scout" in line for line in data["state"]["logs"])


def test_free_stack_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/free-stack")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "fully_free_local_first"
    assert data["approval_required_for_actions"] is True
    assert "capabilities" in data
    assert "next_best_steps" in data
    assert data["source_first"]["mode"] == "source_first_free_local"
    allowed_now = set(data["free_tool_decisions"]["allowed_now"])
    assert {
        "gemma",
        "git_cli_safety_workflow",
        "harper",
        "scrapegraphai",
        "hugging_face_papers",
        "benchlm",
        "open_source_alternative_directories",
    }.issubset(allowed_now)


def test_free_tools_decision_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/free-tools")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "fully_free_local_first"
    assert "harper" in data["allowed_now"]
    assert "mirofish" in data["optional_labs"]
    assert "cosmos3" in data["optional_free_labs"]
    assert "exo_local_ai_cluster" in data["optional_free_labs"]
    assert "ray_local_cluster" in data["optional_free_labs"]
    assert "qwebbridge" in data["adapter_candidates"]
    assert "gemma4_12b" in data["adapter_candidates"]
    assert "claude-opus-4.8" in data["blocked"]
    assert "rocket_new" in data["blocked"]
    assert "sensor_tower" in data["blocked"]
    assert "unabyss_mcp" in data["blocked"]
    assert "rethread" in data["blocked"]
    assert "bluedot" in data["blocked"]
    assert "gitreverse" in data["blocked"]
    assert "gitkraken" in data["blocked"]
    assert "sourcetree" in data["blocked"]
    assert "hyperspace_pods" in data["blocked"]
    assert "n8n" in data["blocked"]
    assert data["counts"]["project_count"] == 7
    assert data["counts"]["ecosystem_topics"] == 34
    assert data["counts"]["developer_toolbox_topics"] == 7
    assert data["counts"]["project_unique_tools"] >= 20
    assert "neuroseed" in data["project_applications"]
    assert "unabyss_mcp" not in data["project_applications"]["kattappa"]
    assert "local_repo_prompt_exporter" in data["project_applications"]["kattappa"]
    assert "homebrew" in data["project_applications"]["kattappa"]
    assert "git_cli_safety_workflow" in data["project_applications"]["kattappa"]
    assert "github_desktop" in data["project_applications"]["kattappa"]
    assert "exo_local_ai_cluster" in data["project_applications"]["kattappa"]
    assert "ray_local_cluster" in data["project_applications"]["kattappa"]
    assert "node_red" in data["project_applications"]["kattappa"]
    assert "sqlite_builtin_backend" in data["project_applications"]["kattappa"]
    assert "pocketbase_optional_backend" in data["project_applications"]["kattappa"]
    assert "local_product_analytics" in data["project_applications"]["kattappa"]
    assert "local_workflow_queue" in data["project_applications"]["kattappa"]
    assert "local_multi_agent_orchestrator" in data["project_applications"]["kattappa"]
    assert "manual_export_billing_playbook" in data["project_applications"]["kattappa"]
    assert "n8n" not in data["project_applications"]["kattappa"]
    assert "cosmos3" in data["project_applications"]["dews"]
    assert "local_product_analytics" in data["project_applications"]["musical-keyboard"]
    assert "pocketbase_optional_backend" not in data["project_applications"]["musical-keyboard"]
    assert "piezoelectric_sensors" in data["project_unique_tools"]
    topic_audit = data["ai_ecosystem_topic_audit"]
    assert len(topic_audit["topics"]) == 34
    assert any(
        topic["topic"] == "n8n" and topic["free_replacements"] == ["node_red"]
        for topic in topic_audit["topics"]
    )
    replacement_policy = data["paid_tool_replacement_policy"]
    assert "search for a fully free/open-source/local-first alternative" in replacement_policy["rule"]
    assert replacement_policy["known_replacements"]["gitreverse"] == ["local_repo_prompt_exporter"]
    assert replacement_policy["known_replacements"]["n8n"] == ["node_red"]
    assert "exo_local_ai_cluster" in replacement_policy["known_replacements"]["hyperspace_pods"]
    developer_toolbox = data["developer_toolbox_audit"]
    assert len(developer_toolbox["topics"]) == 7
    assert "pocketbase_optional_backend" in developer_toolbox["free_capabilities"]
    assert any(
        topic["topic"] == "Stripe" and topic["free_replacements"] == ["manual_export_billing_playbook"]
        for topic in developer_toolbox["topics"]
    )
    blocked = set(data["blocked"])
    assert "stripe" in blocked
    assert "inngest_core_dependency" in blocked
    assert "google_antigravity_core_dependency" in blocked
    for tools in data["project_applications"].values():
        assert "git_cli_safety_workflow" in tools
        assert "github_desktop" in tools
        assert blocked.isdisjoint(tools)


def test_local_model_profiles_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/ai-engine/local-models")
    assert response.status_code == 200
    data = response.json()
    assert data["local_only"] is True
    assert {profile["key"] for profile in data["profiles"]} == {"gemma", "qwen", "deepseek"}


def test_writing_check_local_fallback() -> None:
    client = TestClient(app)
    response = client.post("/writing/check", json={"text": "i dont  want the the typo"})
    assert response.status_code == 200
    data = response.json()
    assert data["network_required"] is False
    assert data["issue_count"] >= 3
    assert "I do not want the typo" in data["corrected_text"]


def test_simulation_lab_local_fallback() -> None:
    client = TestClient(app)
    status_response = client.get("/simulation/status")
    assert status_response.status_code == 200
    assert status_response.json()["license"] == "AGPL-3.0"

    run_response = client.post(
        "/simulation/run",
        json={"seed": "Kattappa adds Harper and ScrapeGraphAI", "horizon": "short"},
    )
    assert run_response.status_code == 200
    data = run_response.json()
    assert data["engine"] in {"kattappa-local-simulation-fallback", "mirofish-adapter"}
    assert data["scenario"]["seed"].startswith("Kattappa")
    assert data["predictions"]


def test_source_first_policy_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/source-policy")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "source_first_free_local"
    assert any("Build" in rule or "built-in" in rule for rule in data["rules"])
    assert "No paid API dependency." in data["hard_no"]
    assert "No license-blind copying from the internet." in data["hard_no"]


def test_tool_scout_endpoint_creates_build_own_proposal() -> None:
    client = TestClient(app)
    response = client.post(
        "/tool-scout/run",
        json={"task": "fix a coding bug and run tests with a local agent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"proposed", "skipped_duplicate"}

    status_response = client.get("/tool-scout", params={"limit": 10})
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["license_safe"] is True
    assert "Do not copy unknown external code" in status["copying_rule"]
    assert status["catalog"]


def test_tool_adoption_observes_before_final_approval() -> None:
    client = TestClient(app)
    scout_response = client.post(
        "/tool-scout/run",
        json={"task": "build browser automation adapter and test it"},
    )
    assert scout_response.status_code == 200
    scout_data = scout_response.json()
    if scout_data["status"] == "skipped_duplicate":
        reports = client.get("/tool-scout", params={"limit": 1}).json()["reports"]
        report_id = reports[0]["id"]
    else:
        report_id = scout_data["report"]["id"]

    adopt_response = client.post(f"/tool-scout/{report_id}/adopt")
    assert adopt_response.status_code == 200
    adoption = adopt_response.json()
    assert adoption["status"] == "waiting_final_approval"
    assert "Observation stage completed without approval" in adoption["job"]["install_observation"]
    assert adoption["job"]["test_result"]
    final_approval = adoption["job"]["final_approval_id"]

    final_decision = client.post(f"/approvals/{final_approval}", json={"status": "approved"})
    assert final_decision.status_code == 200

    final_response = client.post(f"/tool-adoptions/approved/{final_approval}")
    assert final_response.status_code == 200
    final = final_response.json()
    assert final["status"] == "added_to_kattappa"
    assert final["skill_id"]


def test_local_chat_history_lifecycle() -> None:
    client = TestClient(app)
    create_response = client.post("/chat-sessions", json={"title": "New chat"})
    assert create_response.status_code == 200
    session = create_response.json()["item"]

    message_response = client.post(
        f"/chat-sessions/{session['id']}/messages",
        json={"role": "user", "content": "explain embedded systems"},
    )
    assert message_response.status_code == 200

    list_response = client.get("/chat-sessions", params={"limit": 10})
    assert list_response.status_code == 200
    sessions = list_response.json()["items"]
    assert any(item["id"] == session["id"] for item in sessions)

    detail_response = client.get(f"/chat-sessions/{session['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["messages"][0]["content"] == "explain embedded systems"
    assert detail["item"]["title"].startswith("explain embedded")


def test_saved_chat_history_feeds_memory_context() -> None:
    client = TestClient(app)
    create_response = client.post("/chat-sessions", json={"title": "Board repair note"})
    assert create_response.status_code == 200
    session = create_response.json()["item"]

    message_response = client.post(
        f"/chat-sessions/{session['id']}/messages",
        json={"role": "user", "content": "Remember the aurora regulator board has a short near C23."},
    )
    assert message_response.status_code == 200

    context_response = client.get("/memory/context", params={"q": "aurora regulator C23"})
    assert context_response.status_code == 200
    context = context_response.json()["context"]
    assert "Relevant saved chat history" in context
    assert "aurora regulator board" in context


def test_long_task_lifecycle_and_context() -> None:
    client = TestClient(app)
    create_response = client.post(
        "/long-tasks",
        json={
            "title": "Finish local memory system",
            "goal": "Store every chat locally and resume older long tasks.",
            "priority": "high",
        },
    )
    assert create_response.status_code == 200
    task = create_response.json()["item"]
    assert task["status"] == "active"

    update_response = client.post(
        f"/long-tasks/{task['id']}",
        json={"progress": "SQLite task ledger added.", "next_step": "Expose task resume UI."},
    )
    assert update_response.status_code == 200
    updated = update_response.json()["item"]
    assert updated["progress"] == "SQLite task ledger added."

    search_response = client.get("/long-tasks/search", params={"q": "resume older tasks"})
    assert search_response.status_code == 200
    assert any(item["id"] == task["id"] for item in search_response.json()["items"])

    context_response = client.get("/memory/context", params={"q": "continue local memory system"})
    assert context_response.status_code == 200
    assert "Active or related long tasks" in context_response.json()["context"]


def test_missing_install_flow_is_approval_gated() -> None:
    client = TestClient(app)
    response = client.post("/install/missing/request")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ready", "approval_required"}
    assert data["plan"]["free_local_only"] is True
    assert data["plan"]["source_first"]["mode"] == "source_first_free_local"
    assert "steps" in data["plan"]
    assert "manual_steps" in data["plan"]

    noop_response = client.post("/install/approved/not-an-install-job")
    assert noop_response.status_code == 200
    assert noop_response.json()["status"] == "not_install_job"


def test_capability_ladder_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/capability-ladder")
    assert response.status_code == 200
    data = response.json()
    assert data["fully_free_only"] is True
    assert "not true AGI or ASI" in data["truth_boundary"]
    assert isinstance(data["maturity_percent"], int)
    assert data["levels"]
    assert "next_actions" in data


def test_builder_profile_and_workspace_map() -> None:
    client = TestClient(app)
    profile_response = client.get("/builder/profile")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["name"] == "Kattappa Builder Brain"
    assert "not OpenAI private code" in profile["truth_boundary"]
    assert "personal and professional assistant" in profile["motive"]
    assert "manager_worker" in profile["worker_model"]
    assert "improvement_worker" in profile["worker_model"]
    assert profile["protocol"]

    map_response = client.get("/builder/workspace-map", params={"limit": 5})
    assert map_response.status_code == 200
    workspace = map_response.json()
    assert workspace["files_shown"] <= 5
    assert workspace["main_systems"]


def test_project_index_and_search() -> None:
    client = TestClient(app)
    response = client.get("/project-index", params={"limit": 120})
    assert response.status_code == 200
    data = response.json()
    assert data["files_indexed"] > 0
    assert any(item["path"] == "backend/main.py" and item["exists"] for item in data["important_files"])
    assert data["scripts"]

    search_response = client.get("/project-index/search", params={"q": "desktop app", "limit": 10})
    assert search_response.status_code == 200
    assert "items" in search_response.json()


def test_long_task_resume_planner() -> None:
    client = TestClient(app)
    create_response = client.post(
        "/long-tasks",
        json={
            "title": "Make Kattappa rival ChatGPT locally",
            "goal": "Add project intelligence, local memory, and resumable task execution.",
            "priority": "high",
        },
    )
    assert create_response.status_code == 200
    task = create_response.json()["item"]

    resume_response = client.post(f"/long-tasks/{task['id']}/resume")
    assert resume_response.status_code == 200
    data = resume_response.json()
    assert data["task"]["status"] == "active"
    assert data["next_steps"]
    assert "resume_prompt" in data


def test_project_ecosystem_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/projects/ecosystem")
    assert response.status_code == 200
    data = response.json()
    assert data["build_first"].startswith("Kattappa AI OS")
    assert len(data["projects"]) == 7
    assert data["projects"][0]["id"] == "kattappa"
    assert data["projects"][-1]["id"] == "neuroseed"
    assert "No destructive emitters" in data["projects"][-2]["safety_boundary"]
    assert "No memory upload claims" in data["projects"][-1]["safety_boundary"]
    assert "free_tool_rule" in data
    assert "must be fully free" in data["free_tool_rule"]
    assert "search for a similar fully free replacement" in data["free_tool_rule"]
    assert data["projects"][0]["free_tools"]
    kattappa = data["projects"][0]
    assert "local_multi_agent_orchestrator" in kattappa["free_tools"]
    assert "pocketbase_optional_backend" in kattappa["free_tools"]


def test_builder_agent_route() -> None:
    client = TestClient(app)
    response = client.post("/chat", json={"message": "explain your builder brain and how you work"})
    assert response.status_code == 200
    data = response.json()
    assert data["state"]["selected_agent"] == "builder"
    assert "Builder Brain" in data["response"]


def test_main_agent_router_selects_related_agents() -> None:
    cases = {
        "explain embedded firmware for a sensor": "coder",
        "click the settings button on desktop": "desktop",
        "search web for latest local ai tools": "researcher",
        "explain your builder brain workflow": "builder",
        "hello how are you": "evaluator",
    }
    for prompt, expected in cases.items():
        decision = route_task(prompt)
        assert decision["agent"] == expected
        assert "scores" in decision


def test_improvement_lifecycle() -> None:
    client = TestClient(app)
    create_response = client.post(
        "/improvements",
        json={
            "title": "Add better OCR fallback",
            "motive": "Improve cursor guidance without cloud services.",
            "proposal": "Add a local OCR fallback path and tests.",
            "risk": "low",
        },
    )
    assert create_response.status_code == 200
    item = create_response.json()["item"]
    assert item["status"] == "pending"

    list_response = client.get("/improvements", params={"status": "pending", "limit": 10})
    assert list_response.status_code == 200
    pending_ids = {entry["id"] for entry in list_response.json()["items"]}
    assert item["id"] in pending_ids

    decision_response = client.post(f"/improvements/{item['id']}", json={"status": "approved", "publish": False})
    assert decision_response.status_code == 200
    assert decision_response.json()["item"]["status"] == "approved"
    assert decision_response.json()["publish"]["published"] is False


def test_project_improvement_agents_observe_and_check_local_registry() -> None:
    client = TestClient(app)
    registry_response = client.get("/projects/improvement-agents")
    assert registry_response.status_code == 200
    registry = registry_response.json()
    assert registry["mode"] == "standalone_approval_gated_improvement_agent"
    assert registry["local_registry"] == "docs/IMPROVEMENT_REGISTRY.md"
    assert list(registry["projects"]) == ["kattappa"]

    observe_response = client.post("/projects/improvement-agents/observe", json={"run_status": False})
    assert observe_response.status_code == 200
    observation = observe_response.json()
    assert observation["observed_projects"] == 1
    assert observation["approval_required_before_apply"] is True
    assert observation["auto_apply"] is False
    assert observation["publish_after_approval"] == "docs/IMPROVEMENT_REGISTRY.md"
    assert all("checks" in item for item in observation["observations"])

    shared_response = client.post("/projects/improvement-agents/check-shared")
    assert shared_response.status_code == 200
    shared = shared_response.json()
    assert shared["checked"] is True
    assert shared["auto_apply"] is False
    assert shared["approval_required_before_adoption"] is True
    assert "local_entries" in shared


def test_skill_reflection_and_evolution_lifecycle() -> None:
    client = TestClient(app)
    skill_response = client.post(
        "/skills",
        json={
            "name": "Debug Python Test Failure",
            "trigger": "pytest failure",
            "steps": "Read failure, inspect code, patch minimal fix, rerun tests.",
            "tools": "pytest, local files",
            "risk": "medium",
        },
    )
    assert skill_response.status_code == 200
    skill = skill_response.json()["item"]
    assert skill["trust"] == "draft"

    trust_response = client.post(f"/skills/{skill['id']}/trust", json={"trust": "approved"})
    assert trust_response.status_code == 200
    assert trust_response.json()["item"]["trust"] == "approved"

    result_response = client.post(
        f"/skills/{skill['id']}/result",
        json={"success": True, "reflection": "The test failed because an endpoint contract changed."},
    )
    assert result_response.status_code == 200
    assert result_response.json()["item"]["success_count"] >= 1

    reflection_response = client.post(
        "/reflections",
        json={
            "task": "recurring screen OCR failure",
            "outcome": "failure",
            "lesson": "Check Tesseract executable before attempting OCR actions.",
        },
    )
    assert reflection_response.status_code == 200

    evolution_response = client.post("/self-evolution/run", params={"limit": 20})
    assert evolution_response.status_code == 200
    cycle = evolution_response.json()
    assert cycle["fully_free_only"] is True
    assert cycle["cycle"] == "read_execute_reflect_write"
    assert cycle["cluster_sync"]["auto_share_with_paired_nodes"] is False
    assert cycle["cluster_sync"]["auto_apply_on_receiving_nodes"] is False
    assert cycle["cluster_sync"]["canonical_distribution"] == "local_project_registry"
    assert "write_to_docs_improvement_registry" in cycle["cluster_sync"]["publish_flow"]
    assert "approved_skills" in cycle["cluster_sync"]["shared_data"]
    assert "raw_user_chat_history" in cycle["cluster_sync"]["never_auto_share"]
    assert "ask_local_approval" in cycle["cluster_sync"]["receiving_node_flow"]
    assert cycle["cluster_sync"]["git_repo_distribution"]["enabled"] is False
    assert cycle["cluster_sync"]["git_repo_distribution"]["path"] == "docs/IMPROVEMENT_REGISTRY.md"
    assert cycle["cluster_sync"]["git_repo_distribution"]["applies_to"] == "local_kattappa_project_only"
    assert cycle["cluster_sync"]["git_repo_distribution"]["direct_push_to_other_systems"] is False
    assert cycle["cluster_sync"]["git_repo_distribution"]["unpaired_check_policy"]["default_interval_hours"] == 24
    assert cycle["cluster_sync"]["git_repo_distribution"]["unpaired_check_policy"]["if_new_data_found"] == "ask_local_approval"
    assert cycle["cluster_sync"]["git_repo_distribution"]["paired_check_policy"]["default_interval_hours"] == 24
    assert cycle["cluster_sync"]["git_repo_distribution"]["paired_check_policy"]["if_new_data_found"] == "ask_local_approval"
    assert "draft_skills_created" in cycle
