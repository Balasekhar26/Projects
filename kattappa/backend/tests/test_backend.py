import json

from fastapi.testclient import TestClient

from backend.agents import desktop as desktop_module
from backend.agents.planner import route_task
from backend import main as backend_main
from backend.core import cluster_runtime as cluster_runtime_module
from backend.core.memory import memory
from backend.core.operator import build_operator_plan
from backend.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Kattappa AI OS backend running"
    assert "memory_count" in data


def test_voice_backend_pipeline_endpoints(monkeypatch) -> None:
    monkeypatch.setattr(
        backend_main,
        "speak",
        lambda text, purpose="assistant_response": f"spoken:{purpose}:{text}",
    )
    client = TestClient(app)
    status_response = client.get("/voice/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["mode"] == "local_backend_voice_pipeline"
    assert status["primary_path"] == "desktop_microphone_to_backend_openwakeword_stt_tts"
    assert status["browser_speech_primary"] is False
    assert status["wake"]["engine"] == "openwakeword"
    assert status["wake"]["primary_decision"] in {"openwakeword_custom_models", "local_stt_wake_name_parser"}
    assert status["wake"]["fallback_engine"] == "local_stt_wake_name_parser"
    assert status["profile"]["primary_spoken_language"] == "Telugu"
    assert status["profile"]["secondary_spoken_language"] == "English"
    assert status["profile"]["text_output_language"] == "English"
    assert status["stt"]["engine"] == "faster-whisper"
    assert status["stt"]["fallback"] == "typed_chat"
    assert status["tts"]["preferred_engine"] == "piper"
    assert status["tts"]["primary_decision"] in {"piper_local_model", "pyttsx3_or_native_os"}
    assert status["language_contract"]["primary_spoken_language"] == "Telugu"
    assert status["language_contract"]["secondary_spoken_language"] == "English"
    assert status["language_contract"]["text_output_language"] == "English"

    speak_response = client.post(
        "/voice/speak",
        json={"text": "I am ready.", "purpose": "assistant_response"},
    )
    assert speak_response.status_code == 200
    spoken = speak_response.json()
    assert spoken["spoken_text"].startswith("సరే.")
    assert spoken["result"].startswith("spoken:assistant_response:సరే.")

    parse_response = client.post("/voice/parse-wake", json={"transcript": "Mama check status"})
    assert parse_response.status_code == 200
    parsed = parse_response.json()
    assert parsed["wake_detected"] is True
    assert parsed["wake_name"] == "mama"
    assert parsed["command"] == "check status"


def test_builder_analytics_is_local_and_free() -> None:
    client = TestClient(app)
    response = client.get("/builder/analytics")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "fully_free_local_builder_profile"
    assert data["cost"] == "free"
    assert "No code" in data["privacy_boundary"]
    assert "hosted transcript analytics" in data["blocked_core_dependencies"]
    assert {item["key"] for item in data["dimensions"]} == {
        "planning",
        "execution",
        "engineering_quality",
        "product_instinct",
        "steering",
    }
    assert len(data["projects"]) == 7
    replacements = {item["source"]: item for item in data["free_replacements"]}
    assert "Paxel-style AI coding analytics" in replacements
    assert replacements["Paxel-style AI coding analytics"]["fully_free_replacement"] == "Kattappa Local Builder Profile"


def test_approval_lifecycle() -> None:
    client = TestClient(app)
    chat_response = client.post("/chat", json={"message": "explain embedded systems then delete"})
    assert chat_response.status_code == 200
    state = chat_response.json()["state"]
    approval_id = state["approval_id"]
    assert state["approval_required"] is True
    assert approval_id

    pending_response = client.get("/approvals", params={"status": "pending", "limit": 5})
    assert pending_response.status_code == 200
    pending_ids = {item["id"] for item in pending_response.json()["items"]}
    assert approval_id in pending_ids

    waiting_response = client.post(f"/approvals/{approval_id}/continue")
    assert waiting_response.status_code == 200
    assert waiting_response.json()["status"] == "waiting_for_approval"

    decision_response = client.post(f"/approvals/{approval_id}", json={"status": "approved"})
    assert decision_response.status_code == 200
    decision = decision_response.json()
    assert decision["item"]["status"] == "approved"
    continued = decision["continuation"]
    assert continued["kind"] == "chat"
    assert continued["status"] == "completed"
    assert continued["state"]["approval_required"] is False
    assert continued["state"]["approval_id"] is None
    assert "exact delete target" in continued["response"]
    assert any("approved continuation" in line for line in continued["state"]["logs"])

    continue_response = client.post(f"/approvals/{approval_id}/continue")
    assert continue_response.status_code == 200
    assert continue_response.json()["status"] == "already_continued"


def test_non_chat_approval_uses_registered_continuation_kind() -> None:
    client = TestClient(app)
    approval_id = memory.create_approval(
        "Install missing free/local Kattappa AI OS capabilities.",
        "medium",
        continuation_type="install_job",
    )
    decision_response = client.post(f"/approvals/{approval_id}", json={"status": "approved"})
    assert decision_response.status_code == 200
    continuation = decision_response.json()["continuation"]
    assert continuation["kind"] == "install_job"
    assert continuation["status"] == "not_install_job"

    continue_response = client.post(f"/approvals/{approval_id}/continue")
    assert continue_response.status_code == 200
    assert continue_response.json()["status"] == "already_continued"


def test_self_improvement_approval_continues_to_approved_registry() -> None:
    client = TestClient(app)
    improvement_id = memory.create_improvement(
        title="Approval continuation test",
        motive="Verify approval resumes self-improvement work.",
        proposal="Record the approved proposal and keep code changes gated.",
        risk="medium",
    )
    skill_id = memory.create_skill(
        name="Approval Continuation Test Skill",
        trigger="approval continuation test",
        steps="Use only after approval.",
        tools="local memory",
        risk="medium",
        trust="draft",
    )
    approval_id = memory.create_approval(
        action=f"Review self-improvement proposal {improvement_id} and draft skill {skill_id}: test",
        risk="medium",
        continuation_type="self_improvement",
        continuation_payload=json.dumps({"improvement_id": improvement_id, "skill_id": skill_id}),
    )

    decision_response = client.post(f"/approvals/{approval_id}", json={"status": "approved"})
    assert decision_response.status_code == 200
    continuation = decision_response.json()["continuation"]
    assert continuation["kind"] == "self_improvement"
    assert continuation["status"] == "continued"
    assert continuation["improvement"]["status"] == "approved"
    assert continuation["skill"]["trust"] == "approved"


def test_self_evolution_approval_approves_draft_skill() -> None:
    client = TestClient(app)
    skill_id = memory.create_skill(
        name="Self Evolution Continuation Skill",
        trigger="self evolution continuation",
        steps="Run after approval.",
        tools="local memory",
        risk="medium",
        trust="draft",
    )
    approval_id = memory.create_approval(
        action=f"Review and approve draft self-evolution skill {skill_id}: self evolution continuation",
        risk="medium",
        continuation_type="self_evolution",
        continuation_payload=json.dumps({"skill_id": skill_id}),
    )

    decision_response = client.post(f"/approvals/{approval_id}", json={"status": "approved"})
    assert decision_response.status_code == 200
    continuation = decision_response.json()["continuation"]
    assert continuation["kind"] == "self_evolution"
    assert continuation["status"] == "continued"
    assert continuation["skill"]["trust"] == "approved"


def test_operator_plan_endpoint() -> None:
    client = TestClient(app)
    response = client.post("/operator/plan", json={"message": "guide me with cursor to open settings"})
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["execution_path"] == "human_guided_step"
    assert plan["action_required"] is True
    assert plan["local_only"] is True
    assert "next_steps" in plan


def test_operator_plan_ignores_legacy_mode_prefix() -> None:
    client = TestClient(app)
    response = client.post("/operator/plan", json={"message": "[operator mode: autonomous]\nwhat is 2 + 2"})
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["execution_path"] == "reply_only"
    assert plan["needs_approval"] is False


def test_cursor_guidance_requires_real_screen_target() -> None:
    plan = build_operator_plan(
        "guide me with cursor to open settings",
        selected_agent="desktop",
        screen_snapshot={"text": "No matching text", "width": 0, "height": 0, "words": []},
    )
    guidance = plan["visual_guidance"]
    assert guidance["enabled"] is False
    assert guidance["reason"] == "No reliable screen target was found."


def test_cursor_guidance_uses_matched_ocr_target() -> None:
    plan = build_operator_plan(
        "show me where to click settings",
        selected_agent="desktop",
        screen_snapshot={
            "text": "Settings",
            "width": 1000,
            "height": 700,
            "words": [
                {"text": "Settings", "left": 100, "top": 140, "width": 120, "height": 32, "confidence": 92}
            ],
        },
    )
    guidance = plan["visual_guidance"]
    assert guidance["enabled"] is True
    assert guidance["matched_screen_text"] is True
    assert guidance["target"]["label"] == "Settings"
    assert guidance["target"]["source"] == "ocr"


def test_chat_returns_operator_plan() -> None:
    client = TestClient(app)
    response = client.post("/chat", json={"message": "guide me with cursor to inspect the screen"})
    assert response.status_code == 200
    state = response.json()["state"]
    assert state["selected_agent"] == "desktop"
    assert state["operator_plan"]["execution_path"] == "human_guided_step"
    assert state["operator_plan"]["local_only"] is True


def test_desktop_reply_hides_ocr_failure_noise(monkeypatch) -> None:
    monkeypatch.setattr(
        desktop_module,
        "read_screen_snapshot",
        lambda: {
            "text": "Screenshot saved to /tmp/current_screen.png; OCR failed: tesseract missing",
            "screenshot_path": "/tmp/current_screen.png",
            "width": 0,
            "height": 0,
            "words": [],
            "error": "tesseract missing",
        },
    )
    state = desktop_module.desktop_node(
        {
            "user_input": "guide me with cursor to open settings",
            "selected_agent": "desktop",
            "memory_context": None,
            "risk_level": "low",
            "memory_query": "guide me with cursor to open settings",
            "chat_session_id": "",
            "current_chat_message_id": "",
            "logs": [],
        }
    )
    assert state["approval_required"] is False
    assert state["operator_plan"]["screen_context_available"] is False
    assert "OCR unavailable" not in state["result"]
    assert "Screen captured" not in state["result"]
    assert "I can guide this without controlling" not in state["result"]


def test_embedded_systems_uses_built_in_local_answer() -> None:
    client = TestClient(app)
    response = client.post("/chat", json={"message": "explain embedded systems"})
    assert response.status_code == 200
    data = response.json()
    assert data["state"]["selected_agent"] == "coder"
    assert "dedicated computer inside a device" in data["response"]


def test_embedded_systems_more_uses_deeper_local_answer() -> None:
    client = TestClient(app)
    response = client.post("/chat", json={"message": "tell me more about embedded systems"})
    assert response.status_code == 200
    data = response.json()
    assert data["state"]["selected_agent"] == "coder"
    assert "Here is the next layer" in data["response"]
    assert "Peripherals" in data["response"]


def test_remember_command_stores_user_memory() -> None:
    client = TestClient(app)
    response = client.post(
        "/chat",
        json={"message": "Remember the project codename bluefalcon42 for this history test."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"]["selected_agent"] == "memory"
    assert "bluefalcon42" in data["response"]
    assert any("bluefalcon42" in item for item in memory.recall("bluefalcon42 history test", n_results=10))


def test_approved_ambiguous_delete_does_not_silently_ignore_action() -> None:
    client = TestClient(app)
    response = client.post("/chat", json={"message": "explain embedded systems then delete"})
    assert response.status_code == 200
    state = response.json()["state"]
    assert state["selected_agent"] == "file"
    assert state["approval_required"] is True
    approval_id = state["approval_id"]

    decision_response = client.post(f"/approvals/{approval_id}", json={"status": "approved"})
    assert decision_response.status_code == 200
    continuation = decision_response.json()["continuation"]
    assert continuation["status"] == "completed"
    assert "exact delete target" in continuation["response"]


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
        "local_deck_generator",
        "mermaid_diagram_generator",
        "local_context_compressor",
        "local_schedule_planner",
        "local_code_review",
        "local_gsd_workflow",
        "local_document_markdown",
        "local_marketing_kit",
        "local_network_scanner",
        "local_friday_voice_assistant_patterns",
        "local_blackbox_coding_assistant",
        "local_personal_assistant_patterns",
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
    assert "markitdown_optional_adapter" in data["adapter_candidates"]
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
    assert data["counts"]["developer_toolbox_topics"] == 26
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
    assert "local_deck_generator" in data["project_applications"]["kattappa"]
    assert "mermaid_diagram_generator" in data["project_applications"]["kattappa"]
    assert "local_context_compressor" in data["project_applications"]["kattappa"]
    assert "local_schedule_planner" in data["project_applications"]["kattappa"]
    assert "ui_tars_inspired_operator_policy" in data["project_applications"]["kattappa"]
    assert "local_code_review" in data["project_applications"]["kattappa"]
    assert "local_gsd_workflow" in data["project_applications"]["kattappa"]
    assert "local_document_markdown" in data["project_applications"]["kattappa"]
    assert "local_marketing_kit" in data["project_applications"]["kattappa"]
    assert "local_friday_voice_assistant_patterns" in data["project_applications"]["kattappa"]
    assert "local_blackbox_coding_assistant" in data["project_applications"]["kattappa"]
    assert "local_personal_assistant_patterns" in data["project_applications"]["kattappa"]
    assert "n8n" not in data["project_applications"]["kattappa"]
    assert "local_network_scanner" in data["project_applications"]["ai-cyber-shield"]
    assert "nmap_optional_adapter" in data["project_applications"]["ai-cyber-shield"]
    assert "cosmos3" in data["project_applications"]["dews"]
    assert "ui_tars_inspired_operator_policy" in data["project_applications"]["dews"]
    assert "local_product_analytics" in data["project_applications"]["musical-keyboard"]
    assert "pocketbase_optional_backend" not in data["project_applications"]["musical-keyboard"]
    assert "openbci_mne_research_adapter" in data["project_applications"]["neuroseed"]
    assert "local_document_markdown" in data["project_applications"]["neuroseed"]
    assert "local_marketing_kit" in data["project_applications"]["neuroseed"]
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
    assert len(developer_toolbox["topics"]) == 26
    assert "pocketbase_optional_backend" in developer_toolbox["free_capabilities"]
    assert "local_deck_generator" in developer_toolbox["free_capabilities"]
    assert "mermaid_diagram_generator" in developer_toolbox["free_capabilities"]
    assert "local_context_compressor" in developer_toolbox["free_capabilities"]
    assert "openbci_mne_research_adapter" in developer_toolbox["free_capabilities"]
    assert "local_code_review" in developer_toolbox["free_capabilities"]
    assert "local_gsd_workflow" in developer_toolbox["free_capabilities"]
    assert "local_document_markdown" in developer_toolbox["free_capabilities"]
    assert "markitdown_optional_adapter" in developer_toolbox["free_capabilities"]
    assert "local_marketing_kit" in developer_toolbox["free_capabilities"]
    assert "local_network_scanner" in developer_toolbox["free_capabilities"]
    assert "nmap_optional_adapter" in developer_toolbox["free_capabilities"]
    assert "local_friday_voice_assistant_patterns" in developer_toolbox["free_capabilities"]
    assert "local_blackbox_coding_assistant" in developer_toolbox["free_capabilities"]
    assert "local_personal_assistant_patterns" in developer_toolbox["free_capabilities"]
    assert any(
        topic["topic"] == "Stripe" and topic["free_replacements"] == ["manual_export_billing_playbook"]
        for topic in developer_toolbox["topics"]
    )
    assert any(
        topic["topic"] == "Napkin AI" and "mermaid_diagram_generator" in topic["free_replacements"]
        for topic in developer_toolbox["topics"]
    )
    assert any(
        topic["topic"] == "CodeRabbit" and "local_code_review" in topic["free_replacements"]
        for topic in developer_toolbox["topics"]
    )
    assert any(
        topic["topic"] == "MarkItDown / Marketdown AI"
        and "local_document_markdown" in topic["free_replacements"]
        for topic in developer_toolbox["topics"]
    )
    assert any(
        topic["topic"] == "Pomelli AI" and "local_marketing_kit" in topic["free_replacements"]
        for topic in developer_toolbox["topics"]
    )
    assert any(
        topic["topic"] == "Nmap" and "local_network_scanner" in topic["free_replacements"]
        for topic in developer_toolbox["topics"]
    )
    assert any(
        topic["topic"] == "FRIDAY Tony Stark Demo"
        and "local_friday_voice_assistant_patterns" in topic["free_replacements"]
        for topic in developer_toolbox["topics"]
    )
    assert any(
        topic["topic"] == "BLACKBOX AI"
        and "local_blackbox_coding_assistant" in topic["free_replacements"]
        for topic in developer_toolbox["topics"]
    )
    blocked = set(data["blocked"])
    assert "stripe" in blocked
    assert "inngest_core_dependency" in blocked
    assert "google_antigravity_core_dependency" in blocked
    assert "pitch_ai_core_dependency" in blocked
    assert "gamma_ai_core_dependency" in blocked
    assert "napkin_ai_core_dependency" in blocked
    assert "neuralink_or_neuracle_implant_dependency" in blocked
    assert "coderabbit_core_dependency" in blocked
    assert "gsd_external_framework" in blocked
    assert "ralph_coding_loop_dependency" in blocked
    assert "pomelli_core_dependency" in blocked
    assert "markitdown_required_dependency" in blocked
    assert "nmap_required_dependency" in blocked
    assert "friday_cloud_voice_stack_dependency" in blocked
    assert "blackbox_ai_core_dependency" in blocked
    assert "personal_assistant_repo_code_copying" in blocked
    for tools in data["project_applications"].values():
        assert "git_cli_safety_workflow" in tools
        assert "github_desktop" in tools
        assert blocked.isdisjoint(tools)


def test_local_creator_replacement_endpoints() -> None:
    client = TestClient(app)
    replacements = client.get("/toolbox/replacements")
    assert replacements.status_code == 200
    replacement_data = replacements.json()
    assert replacement_data["mode"] == "fully_free_replacements_for_toolbox_topics"
    assert "local_deck_generator" in replacement_data["added_capabilities"]
    assert "local_code_review" in replacement_data["added_capabilities"]
    assert "local_marketing_kit" in replacement_data["added_capabilities"]
    assert "local_blackbox_coding_assistant" in replacement_data["added_capabilities"]
    assert "neuralink_or_neuracle_implant_dependency" in replacement_data["blocked_from_core"]
    assert "coderabbit_core_dependency" in replacement_data["blocked_from_core"]
    assert "blackbox_ai_core_dependency" in replacement_data["blocked_from_core"]

    deck = client.post(
        "/creator/deck",
        json={
            "topic": "PCB Doctor repair workflow",
            "audience": "technicians",
            "project": "PCB Doctor",
            "slide_count": 5,
        },
    )
    assert deck.status_code == 200
    deck_data = deck.json()
    assert deck_data["engine"] == "kattappa_local_deck_generator"
    assert deck_data["cost"] == "free"
    assert deck_data["network_required"] is False
    assert "## 1." in deck_data["markdown"]

    diagram = client.post(
        "/creator/diagram",
        json={"text": "Capture board image. Detect hotspot. Guide measurement. Export report."},
    )
    assert diagram.status_code == 200
    diagram_data = diagram.json()
    assert diagram_data["engine"] == "kattappa_mermaid_diagram_generator"
    assert diagram_data["mermaid"].startswith("flowchart TD")

    compressed = client.post(
        "/context/compress",
        json={
            "text": "INFO start\nERROR failed build\nERROR failed build\nTODO fix test\nnotes",
            "max_points": 3,
        },
    )
    assert compressed.status_code == 200
    compressed_data = compressed.json()
    assert compressed_data["engine"] == "kattappa_local_context_compressor"
    assert compressed_data["network_required"] is False
    assert compressed_data["selected_points"] == 3
    assert any("ERROR failed build" in point for point in compressed_data["key_points"])

    review = client.post(
        "/creator/code-review",
        json={
            "project": "Kattappa",
            "diff_text": (
                '+ API_KEY = "abcdefghi"\n'
                '+ subprocess.run("rm -rf /", shell=True)\n'
                '+ print("debug")\n'
            ),
        },
    )
    assert review.status_code == 200
    review_data = review.json()
    assert review_data["engine"] == "kattappa_local_code_review"
    assert review_data["network_required"] is False
    assert {finding["rule"] for finding in review_data["findings"]} >= {
        "hardcoded_secret",
        "unsafe_shell",
        "debug_leftover",
    }

    workflow = client.post(
        "/creator/gsd-workflow",
        json={"goal": "Add a local review endpoint", "project": "Kattappa"},
    )
    assert workflow.status_code == 200
    workflow_data = workflow.json()
    assert workflow_data["engine"] == "kattappa_local_gsd_workflow"
    assert [phase["phase"] for phase in workflow_data["phases"]] == [
        "plan",
        "execute",
        "verify",
        "fix",
    ]

    markdown = client.post(
        "/creator/document-markdown",
        json={"filename": "signals.csv", "text": "cue,result\ncued,pass\nuncued,review"},
    )
    assert markdown.status_code == 200
    markdown_data = markdown.json()
    assert markdown_data["engine"] == "kattappa_local_document_markdown"
    assert "| cue | result |" in markdown_data["markdown"]
    assert "| cued | pass |" in markdown_data["markdown"]

    marketing = client.post(
        "/creator/marketing-kit",
        json={
            "brand": "NeuroSeed",
            "product": "consent-first recall trainer",
            "audience": "learners",
            "channel": "release notes",
        },
    )
    assert marketing.status_code == 200
    marketing_data = marketing.json()
    assert marketing_data["engine"] == "kattappa_local_marketing_kit"
    assert marketing_data["network_required"] is False
    assert marketing_data["posts"]
    assert marketing_data["email_subjects"]


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
    final = final_decision.json()["continuation"]
    assert final["kind"] == "tool_adoption"
    assert final["status"] == "added_to_kattappa"
    assert final["skill_id"]


def test_local_chat_history_lifecycle() -> None:
    client = TestClient(app)
    create_response = client.post("/chat-sessions", json={"title": "New chat"})
    assert create_response.status_code == 200
    session = create_response.json()["item"]
    assert session["id"] == "kattappa-main-chat"
    assert session["title"] == "Kattappa Main Chat"

    message_response = client.post(
        f"/chat-sessions/{session['id']}/messages",
        json={"role": "user", "content": "explain embedded systems"},
    )
    assert message_response.status_code == 200

    list_response = client.get("/chat-sessions", params={"limit": 10})
    assert list_response.status_code == 200
    sessions = list_response.json()["items"]
    assert len(sessions) == 1
    assert any(item["id"] == session["id"] for item in sessions)

    detail_response = client.get(f"/chat-sessions/{session['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert any(item["content"] == "explain embedded systems" for item in detail["messages"])
    assert detail["item"]["title"] == "Kattappa Main Chat"


def test_chat_uses_single_history_and_returns_related_messages() -> None:
    client = TestClient(app)
    first_response = client.post("/chat", json={"message": "explain embedded systems"})
    assert first_response.status_code == 200
    first_session = first_response.json()["session"]
    assert first_session["id"] == "kattappa-main-chat"

    second_response = client.post("/chat", json={"message": "tell me more about embedded systems"})
    assert second_response.status_code == 200
    second = second_response.json()
    assert second["session"]["id"] == first_session["id"]
    assert second["state"]["related_messages"]
    assert any("embedded systems" in item["content"].lower() for item in second["state"]["related_messages"])

    sessions_response = client.get("/chat-sessions", params={"limit": 10})
    assert sessions_response.status_code == 200
    assert [item["id"] for item in sessions_response.json()["items"]] == ["kattappa-main-chat"]

    detail_response = client.get(f"/chat-sessions/{first_session['id']}")
    assert detail_response.status_code == 200
    stored = detail_response.json()["messages"]
    assert any(item["role"] == "user" and item["content"] == "explain embedded systems" for item in stored)
    assert any(item["role"] == "user" and item["content"] == "tell me more about embedded systems" for item in stored)


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
    assert "Related older chat history" in context
    assert "aurora regulator board" in context


def test_neuroseed_uses_local_memory_with_consent_boundary() -> None:
    client = TestClient(app)
    reset_response = client.put(
        "/neuroseed/state",
        json={"dataModel": {"version": "pilot-consent-v1", "resetRequested": True}},
    )
    assert reset_response.status_code == 200

    unapproved_payload = {
        "dataModel": {"version": "pilot-consent-v1"},
        "seeds": [
            {
                "id": "seed-blocked",
                "title": "Blocked seed",
                "text": "This seed was never awake approved.",
                "keywords": ["blocked"],
                "cue": {"label": "AUDIO-01"},
                "approved": False,
                "consent": {"status": "pending", "model": "pilot-consent-v1", "approvedAt": None},
                "createdAt": "2026-06-07T10:00:00",
            }
        ],
        "sessions": [
            {
                "id": "session-blocked",
                "startedAt": "2026-06-07T10:05:00",
                "status": "completed",
                "approvedSeedIds": ["seed-blocked"],
                "cueEvents": [
                    {
                        "seedId": "seed-blocked",
                        "seedTitle": "Blocked seed",
                        "cueLabel": "AUDIO-01",
                        "stage": "N2",
                        "cuedAt": "2026-06-07T10:06:00",
                    }
                ],
            }
        ],
        "recallResults": [],
    }
    blocked_response = client.put("/neuroseed/state", json=unapproved_payload)
    assert blocked_response.status_code == 400
    assert "awake-approved" in blocked_response.json()["detail"]

    approved_payload = {
        "dataModel": {"version": "pilot-consent-v1"},
        "seeds": [
            {
                "id": "seed-approved",
                "title": "Autonomy cue",
                "text": "NeuroSeed autonomy identity recall uses awake approved cueing only.",
                "keywords": ["autonomy", "identity", "recall", "cueing"],
                "cue": {"label": "AUDIO-02", "tones": [220, 330]},
                "approved": True,
                "consent": {
                    "status": "awake-approved",
                    "model": "pilot-consent-v1",
                    "approvedAt": "2026-06-07T10:10:00",
                },
                "createdAt": "2026-06-07T10:09:00",
            }
        ],
        "sessions": [
            {
                "id": "session-approved",
                "startedAt": "2026-06-07T10:15:00",
                "endedAt": "2026-06-07T10:18:00",
                "status": "completed",
                "approvedSeedIds": ["seed-approved"],
                "cueEvents": [
                    {
                        "seedId": "seed-approved",
                        "seedTitle": "Autonomy cue",
                        "cueLabel": "AUDIO-02",
                        "stage": "N2",
                        "cuedAt": "2026-06-07T10:16:00",
                    }
                ],
                "settings": {"allowedStages": ["N2", "N3"]},
                "safetyBoundary": {"awakeConsentRequired": True},
            }
        ],
        "recallResults": [
            {
                "id": "recall-approved",
                "sessionId": "session-approved",
                "sessionStartedAt": "2026-06-07T10:15:00",
                "seedId": "seed-approved",
                "seedTitle": "Autonomy cue",
                "condition": "cued",
                "answer": "autonomy identity cueing",
                "score": 0.75,
                "checkedAt": "2026-06-07T18:00:00",
                "consentModel": "pilot-consent-v1",
            }
        ],
    }
    approved_response = client.put("/neuroseed/state", json=approved_payload)
    assert approved_response.status_code == 200
    data = approved_response.json()
    assert data["dataModel"]["durableMemory"] == "universal-ai Chroma + SQLite"
    assert data["seeds"][0]["approved"] is True
    assert data["sessions"][0]["cueEvents"][0]["seedId"] == "seed-approved"
    assert data["recallResults"][0]["condition"] == "cued"
    assert any(log["status"] == "awake-approved" for log in data["consentLogs"])

    search_response = client.get("/memory/search", params={"q": "NeuroSeed autonomy identity", "limit": 10})
    assert search_response.status_code == 200
    assert any("awake approved cueing" in item for item in search_response.json()["items"])

    cleanup_response = client.put(
        "/neuroseed/state",
        json={"dataModel": {"version": "pilot-consent-v1", "resetRequested": True}},
    )
    assert cleanup_response.status_code == 200
    assert cleanup_response.json()["seeds"] == []


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


def test_codex_parity_endpoint_and_rival_routing() -> None:
    client = TestClient(app)
    response = client.get("/builder/codex-parity")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Codex Rival Capability Map"
    assert data["fully_free_only"] is True
    assert data["local_first"] is True
    assert "not OpenAI Codex" in data["truth_boundary"]
    assert data["parity_percent"] >= 50
    keys = {item["key"] for item in data["items"]}
    assert {"coding_loop", "approvals_and_safety", "visible_queue", "self_improvement"} <= keys
    assert data["user_order_contract"]

    routing = route_task("make kattappa rival to codex and list what you can do")
    assert routing["agent"] == "builder"
    builder_score = next(item for item in routing["scores"] if item["agent"] == "builder")
    assert "rival" in builder_score["matches"] or "codex" in builder_score["matches"]

    chat_response = client.post(
        "/chat",
        json={"message": "make kattappa rival to codex and list what you can do"},
    )
    assert chat_response.status_code == 200
    payload = chat_response.json()
    assert payload["state"]["selected_agent"] == "builder"
    assert "Codex Rival Capability Map" in payload["response"]


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
    assert len(data["projects"]) == 12
    assert data["projects"][0]["id"] == "kattappa"
    
    project_ids = {p["id"] for p in data["projects"]}
    assert "neuroseed" in project_ids
    assert "kairo" in project_ids
    assert "prism" in project_ids
    assert "tempo" in project_ids
    assert "portal" in project_ids
    assert "mira" in project_ids

    dews = next(p for p in data["projects"] if p["id"] == "dews")
    neuroseed = next(p for p in data["projects"] if p["id"] == "neuroseed")
    assert "No destructive emitters" in dews["safety_boundary"]
    assert "No memory upload claims" in neuroseed["safety_boundary"]
    assert "free_tool_rule" in data
    assert "must be fully free" in data["free_tool_rule"]
    assert "search for a similar fully free replacement" in data["free_tool_rule"]
    assert data["projects"][0]["free_tools"]
    kattappa = data["projects"][0]
    assert "local_multi_agent_orchestrator" in kattappa["free_tools"]
    assert "pocketbase_optional_backend" in kattappa["free_tools"]
    assert "local_deck_generator" in kattappa["free_tools"]
    assert "mermaid_diagram_generator" in kattappa["free_tools"]
    assert "local_context_compressor" in kattappa["free_tools"]
    assert "local_code_review" in kattappa["free_tools"]
    assert "local_gsd_workflow" in kattappa["free_tools"]
    assert "local_document_markdown" in kattappa["free_tools"]
    assert "local_marketing_kit" in kattappa["free_tools"]
    assert "local_friday_voice_assistant_patterns" in kattappa["free_tools"]
    assert "local_blackbox_coding_assistant" in kattappa["free_tools"]
    assert "local_personal_assistant_patterns" in kattappa["free_tools"]
    cyber_shield = next(p for p in data["projects"] if p["id"] == "ai-cyber-shield")
    assert "local_network_scanner" in cyber_shield["free_tools"]
    assert "openbci_mne_research_adapter" in neuroseed["free_tools"]
    assert "local_document_markdown" in neuroseed["free_tools"]
    assert "local_marketing_kit" in neuroseed["free_tools"]


def test_cluster_runtime_registers_worker_and_keeps_token_private(monkeypatch, tmp_path) -> None:
    client = TestClient(app)
    monkeypatch.setattr(cluster_runtime_module, "_nodes_path", lambda: tmp_path / "cluster_nodes.json")
    monkeypatch.setattr(
        cluster_runtime_module,
        "local_node_profile",
        lambda: {
            "hostname": "test-worker",
            "platform": "test",
            "cpu_count_logical": 8,
            "ram_total_gb": 32.0,
            "capability_tier": "standard_worker",
        },
    )
    token = "test-cluster-token-123"
    register_response = client.post(
        "/cluster/nodes",
        json={
            "name": "Local test worker",
            "base_url": "http://127.0.0.1:8000",
            "token": token,
            "capabilities": {"basic_chat": True, "project_memory": True},
        },
    )
    assert register_response.status_code == 200
    node = register_response.json()["item"]
    assert node["token_configured"] is True
    assert "token" not in node
    assert node["runnable_tasks"] == ["basic_chat", "project_memory"]

    status_response = client.get("/cluster/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["enabled"] is True
    assert status["privacy_contract"]["worker_persistent_chat_storage"] is False

    unauthorized = client.post(
        "/cluster/worker/tasks",
        json={"task_id": "worker-test", "task_kind": "basic_chat", "message": "status"},
    )
    assert unauthorized.status_code == 403

    unauthorized_bid = client.post(
        "/cluster/worker/bid",
        json={"bid_id": "bid-test", "task_kind": "basic_chat", "message": "status"},
    )
    assert unauthorized_bid.status_code == 403

    bid_response = client.post(
        "/cluster/worker/bid",
        headers={"X-Kattappa-Cluster-Token": token},
        json={"bid_id": "bid-test", "task_kind": "basic_chat", "message": "status"},
    )
    assert bid_response.status_code == 200
    bid = bid_response.json()
    assert bid["can_run"] is True
    assert bid["cleanup_policy"]["worker_bid_contains_no_private_result"] is True

    worker_response = client.post(
        "/cluster/worker/tasks",
        headers={"X-Kattappa-Cluster-Token": token},
        json={"task_id": "worker-test", "task_kind": "basic_chat", "message": "status"},
    )
    assert worker_response.status_code == 200
    worker = worker_response.json()
    assert worker["status"] == "completed"
    assert worker["cleanup_receipt"]["task_context_deleted"] is True
    assert worker["cleanup_receipt"]["worker_private_memory_written"] is False
    assert worker["cleanup_receipt"]["worker_chat_history_written"] is False

    delete_response = client.delete(f"/cluster/nodes/{node['id']}")
    assert delete_response.status_code == 200


def test_cluster_manager_delegates_when_local_node_is_too_small(monkeypatch, tmp_path) -> None:
    client = TestClient(app)
    monkeypatch.setattr(cluster_runtime_module, "_nodes_path", lambda: tmp_path / "cluster_nodes.json")
    monkeypatch.setattr(
        cluster_runtime_module,
        "local_node_profile",
        lambda: {
            "hostname": "tiny-manager",
            "platform": "test",
            "cpu_count_logical": 2,
            "ram_total_gb": 4.0,
            "capability_tier": "controller_only",
        },
    )
    monkeypatch.setattr(
        cluster_runtime_module,
        "_post_worker_bid",
        lambda node, payload: {
            "bid_id": payload["bid_id"],
            "can_run": True,
            "reason": "capable",
            "task_kind": payload["task_kind"],
            "score": 95,
            "worker_profile": {
                "hostname": "capable-worker",
                "platform": "test",
                "cpu_count_logical": 16,
                "ram_total_gb": 64.0,
                "capability_tier": "heavy_worker",
            },
            "cleanup_policy": cluster_runtime_module.privacy_contract(),
        },
    )
    monkeypatch.setattr(
        cluster_runtime_module,
        "_post_worker_task",
        lambda node, payload: {
            "status": "completed",
            "task_id": payload["task_id"],
            "result": "worker completed the delegated task",
            "cleanup_receipt": {
                "task_id": payload["task_id"],
                "task_context_deleted": True,
                "worker_private_memory_written": False,
                "worker_chat_history_written": False,
            },
        },
    )
    register_response = client.post(
        "/cluster/nodes",
        json={
            "name": "Capable worker",
            "base_url": "http://127.0.0.1:8001",
            "token": "delegation-token-123",
            "capabilities": {"cpu_count_logical": 16, "ram_total_gb": 64.0},
        },
    )
    assert register_response.status_code == 200
    node = register_response.json()["item"]

    route_response = client.post(
        "/cluster/tasks/route",
        json={"message": "status", "task_kind": "large_local_model"},
    )
    assert route_response.status_code == 200
    routed = route_response.json()
    assert routed["status"] == "delegated"
    assert routed["worker_result"]["result"] == "worker completed the delegated task"
    assert routed["worker_result"]["cleanup_receipt"]["task_context_deleted"] is True
    assert routed["selected_bid"]["score"] == 95
    assert routed["bid_round"]["broadcast_scope"] == "paired_and_unpaired_open_kattappa_nodes"

    sensitive_response = client.post(
        "/cluster/tasks/route",
        json={"message": "read my private password note", "task_kind": "basic_chat", "sensitivity": "sensitive"},
    )
    assert sensitive_response.status_code == 200
    assert sensitive_response.json()["status"] == "not_delegated_sensitive"

    delete_response = client.delete(f"/cluster/nodes/{node['id']}")
    assert delete_response.status_code == 200


def test_cluster_manager_selects_highest_capability_bid(monkeypatch, tmp_path) -> None:
    client = TestClient(app)
    monkeypatch.setattr(cluster_runtime_module, "_nodes_path", lambda: tmp_path / "cluster_nodes.json")
    monkeypatch.setattr(
        cluster_runtime_module,
        "local_node_profile",
        lambda: {
            "hostname": "tiny-manager",
            "platform": "test",
            "cpu_count_logical": 2,
            "ram_total_gb": 4.0,
            "capability_tier": "controller_only",
        },
    )

    for name, url in (("Low worker", "http://127.0.0.1:8011"), ("High worker", "http://127.0.0.1:8012")):
        response = client.post(
            "/cluster/nodes",
            json={
                "name": name,
                "base_url": url,
                "token": f"{name.lower().replace(' ', '-')}-token-123",
                "capabilities": {"cpu_count_logical": 16, "ram_total_gb": 64.0},
            },
        )
        assert response.status_code == 200

    def fake_bid(node, payload):
        score = 98 if node["name"] == "High worker" else 60
        return {
            "bid_id": payload["bid_id"],
            "can_run": True,
            "reason": "capable",
            "task_kind": payload["task_kind"],
            "score": score,
            "worker_profile": {"hostname": node["name"], "cpu_count_logical": 16, "ram_total_gb": 64.0},
            "cleanup_policy": cluster_runtime_module.privacy_contract(),
        }

    monkeypatch.setattr(cluster_runtime_module, "_post_worker_bid", fake_bid)
    monkeypatch.setattr(
        cluster_runtime_module,
        "_post_worker_task",
        lambda node, payload: {
            "status": "completed",
            "task_id": payload["task_id"],
            "result": f"handled by {node['name']}",
            "cleanup_receipt": {
                "task_id": payload["task_id"],
                "task_context_deleted": True,
                "worker_private_memory_written": False,
                "worker_chat_history_written": False,
            },
        },
    )

    route_response = client.post(
        "/cluster/tasks/route",
        json={"message": "use a large model for this", "task_kind": "large_local_model"},
    )

    assert route_response.status_code == 200
    routed = route_response.json()
    assert routed["status"] == "delegated"
    assert routed["worker"]["name"] == "High worker"
    assert routed["selected_bid"]["score"] == 98
    assert routed["worker_result"]["result"] == "handled by High worker"


def test_cluster_pairing_allows_https_public_nodes_but_rejects_public_http(monkeypatch, tmp_path) -> None:
    client = TestClient(app)
    monkeypatch.setattr(cluster_runtime_module, "_nodes_path", lambda: tmp_path / "cluster_nodes.json")

    https_response = client.post(
        "/cluster/nodes",
        json={
            "name": "Remote HTTPS worker",
            "base_url": "https://worker.example.com",
            "token": "remote-https-token-123",
            "capabilities": {"basic_chat": True},
        },
    )
    assert https_response.status_code == 200

    http_response = client.post(
        "/cluster/nodes",
        json={
            "name": "Unsafe public worker",
            "base_url": "http://worker.example.com",
            "token": "remote-http-token-123",
            "capabilities": {"basic_chat": True},
        },
    )
    assert http_response.status_code == 400
    assert "HTTPS" in http_response.json()["detail"]


def test_unpaired_public_worker_uses_one_time_token_and_cleanup(monkeypatch, tmp_path) -> None:
    client = TestClient(app)
    monkeypatch.setattr(cluster_runtime_module, "_public_task_tokens_path", lambda: tmp_path / "public_tokens.json")
    monkeypatch.setattr(
        cluster_runtime_module,
        "local_node_profile",
        lambda: {
            "hostname": "public-worker",
            "platform": "test",
            "cpu_count_logical": 16,
            "ram_total_gb": 64.0,
            "capability_tier": "heavy_worker",
        },
    )

    status_response = client.get("/cluster/public/status")
    assert status_response.status_code == 200
    assert status_response.json()["accepts_task_content_in_bid"] is False

    bid_response = client.post(
        "/cluster/public/bid",
        json={
            "bid_id": "public-bid-1",
            "task_kind": "large_local_model",
            "capability_hint": {"message_included": False},
        },
    )
    assert bid_response.status_code == 200
    bid = bid_response.json()
    assert bid["can_run"] is True
    assert bid["assignment_token"]

    rejected = client.post(
        "/cluster/public/tasks",
        json={"task_id": "public-task-1", "task_kind": "large_local_model", "message": "status"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected_invalid_public_task_token"

    accepted = client.post(
        "/cluster/public/tasks",
        headers={"X-Kattappa-Public-Task-Token": bid["assignment_token"]},
        json={"task_id": "public-task-1", "task_kind": "large_local_model", "message": "status"},
    )
    assert accepted.status_code == 200
    result = accepted.json()
    assert result["status"] == "completed"
    assert result["cleanup_receipt"]["task_context_deleted"] is True
    assert result["cleanup_receipt"]["worker_private_memory_written"] is False

    reused = client.post(
        "/cluster/public/tasks",
        headers={"X-Kattappa-Public-Task-Token": bid["assignment_token"]},
        json={"task_id": "public-task-2", "task_kind": "large_local_model", "message": "status"},
    )
    assert reused.status_code == 200
    assert reused.json()["status"] == "rejected_invalid_public_task_token"


def test_cluster_manager_can_delegate_to_unpaired_discovery_worker_without_broadcasting_message(
    monkeypatch,
    tmp_path,
) -> None:
    client = TestClient(app)
    monkeypatch.setattr(cluster_runtime_module, "_nodes_path", lambda: tmp_path / "cluster_nodes.json")
    monkeypatch.setattr(cluster_runtime_module, "_discovery_targets_path", lambda: tmp_path / "discovery_targets.json")
    monkeypatch.setattr(
        cluster_runtime_module,
        "local_node_profile",
        lambda: {
            "hostname": "tiny-manager",
            "platform": "test",
            "cpu_count_logical": 2,
            "ram_total_gb": 4.0,
            "capability_tier": "controller_only",
        },
    )

    target_response = client.post(
        "/cluster/discovery-targets",
        json={"name": "Unpaired worker", "base_url": "http://127.0.0.1:8031"},
    )
    assert target_response.status_code == 200
    target = target_response.json()["item"]
    assert target["token_required"] is False

    def fake_public_bid(target_node, payload):
        assert "message" not in payload
        assert payload["capability_hint"]["message_included"] is False
        return {
            "bid_id": payload["bid_id"],
            "can_run": True,
            "reason": "capable_without_pairing",
            "task_kind": payload["task_kind"],
            "score": 97,
            "selected_agent": "worker_after_assignment",
            "worker_profile": {"hostname": "unpaired-heavy", "cpu_count_logical": 16, "ram_total_gb": 64.0},
            "assignment_url": "http://127.0.0.1:8031/cluster/public/tasks",
            "assignment_token": "one-time-public-token",
            "cleanup_policy": cluster_runtime_module.privacy_contract(),
        }

    monkeypatch.setattr(cluster_runtime_module, "_post_public_worker_bid", fake_public_bid)
    monkeypatch.setattr(
        cluster_runtime_module,
        "_post_public_worker_task",
        lambda selected_bid, payload: {
            "status": "completed",
            "task_id": payload["task_id"],
            "result": "unpaired worker completed the delegated task",
            "cleanup_receipt": {
                "task_id": payload["task_id"],
                "task_context_deleted": True,
                "worker_private_memory_written": False,
                "worker_chat_history_written": False,
            },
        },
    )

    bids_response = client.post(
        "/cluster/tasks/bids",
        json={"message": "private task text", "task_kind": "large_local_model"},
    )
    assert bids_response.status_code == 200
    visible_bid = bids_response.json()["bids"][0]
    assert visible_bid["worker_kind"] == "unpaired_public_worker"
    assert "assignment_token" not in visible_bid

    route_response = client.post(
        "/cluster/tasks/route",
        json={"message": "use a large model for this", "task_kind": "large_local_model"},
    )
    assert route_response.status_code == 200
    routed = route_response.json()
    assert routed["status"] == "delegated"
    assert routed["run_location"] == "unpaired_public_worker"
    assert routed["worker_result"]["result"] == "unpaired worker completed the delegated task"
    assert routed["worker_result"]["cleanup_receipt"]["task_context_deleted"] is True
    assert "assignment_token" not in routed["selected_bid"]
    assert "assignment_token" not in routed["bid_round"]["bids"][0]

    delete_response = client.delete(f"/cluster/discovery-targets/{target['id']}")
    assert delete_response.status_code == 200


def test_chat_auto_delegates_heavy_work_when_local_system_cannot_run_it(monkeypatch, tmp_path) -> None:
    client = TestClient(app)
    monkeypatch.setattr(cluster_runtime_module, "_nodes_path", lambda: tmp_path / "cluster_nodes.json")
    monkeypatch.setattr(
        cluster_runtime_module,
        "local_node_profile",
        lambda: {
            "hostname": "tiny-manager",
            "platform": "test",
            "cpu_count_logical": 2,
            "ram_total_gb": 4.0,
            "capability_tier": "controller_only",
        },
    )
    monkeypatch.setattr(
        cluster_runtime_module,
        "_post_worker_bid",
        lambda node, payload: {
            "bid_id": payload["bid_id"],
            "can_run": True,
            "reason": "capable",
            "task_kind": payload["task_kind"],
            "score": 99,
            "worker_profile": {"hostname": "remote-heavy", "cpu_count_logical": 16, "ram_total_gb": 64.0},
            "cleanup_policy": cluster_runtime_module.privacy_contract(),
        },
    )
    monkeypatch.setattr(
        cluster_runtime_module,
        "_post_worker_task",
        lambda node, payload: {
            "status": "completed",
            "task_id": payload["task_id"],
            "result": "remote heavy worker answer",
            "state_summary": {"selected_agent": "evaluator", "risk_level": "low", "logs": []},
            "cleanup_receipt": {
                "task_id": payload["task_id"],
                "task_context_deleted": True,
                "worker_private_memory_written": False,
                "worker_chat_history_written": False,
            },
        },
    )
    register_response = client.post(
        "/cluster/nodes",
        json={
            "name": "Heavy opened worker",
            "base_url": "http://127.0.0.1:8021",
            "token": "heavy-worker-token-123",
            "capabilities": {"cpu_count_logical": 16, "ram_total_gb": 64.0},
        },
    )
    assert register_response.status_code == 200

    chat_response = client.post(
        "/chat",
        json={"message": "use a large model to summarize this project"},
    )

    assert chat_response.status_code == 200
    data = chat_response.json()
    assert data["response"] == "remote heavy worker answer"
    assert data["state"]["selected_agent"] == "cluster_worker"
    route = data["state"]["tool_request"]["cluster_route"]
    assert route["status"] == "delegated"
    assert route["worker_result"]["cleanup_receipt"]["task_context_deleted"] is True


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


def test_internet_hub_task_delegation() -> None:
    client = TestClient(app)
    task_id = "test-task-hub-1"
    
    # 1. Post task
    post_res = client.post(
        "/cluster/hub/post-task",
        json={"task_id": task_id, "task_kind": "large_local_model", "min_cpu": 4, "min_ram": 16.0}
    )
    assert post_res.status_code == 200
    task = post_res.json()
    assert task["task_id"] == task_id
    assert task["status"] == "pending"

    # 2. Get pending tasks
    pending_res = client.get("/cluster/hub/pending-tasks")
    assert pending_res.status_code == 200
    pending = pending_res.json()["tasks"]
    assert any(t["task_id"] == task_id for t in pending)

    # 3. Submit bid
    bid_res = client.post(
        "/cluster/hub/bid-task",
        json={
            "task_id": task_id,
            "worker_id": "worker-abc",
            "hostname": "test-node-1",
            "cpu_count": 8,
            "ram_total_gb": 32.0
        }
    )
    assert bid_res.status_code == 200
    assert bid_res.json()["success"] is True

    # 4. Get bids
    bids_res = client.get(f"/cluster/hub/tasks/{task_id}/bids")
    assert bids_res.status_code == 200
    bids = bids_res.json()["bids"]
    assert len(bids) == 1
    assert bids[0]["worker_id"] == "worker-abc"

    # 5. Delegate task payload
    delegate_res = client.post(
        f"/cluster/hub/tasks/{task_id}/delegate",
        json={"worker_id": "worker-abc", "message": "perform sorting task"}
    )
    assert delegate_res.status_code == 200
    assert delegate_res.json()["success"] is True

    # 6. Fetch payload
    payload_res = client.get(f"/cluster/hub/tasks/{task_id}/payload", params={"worker_id": "worker-abc"})
    assert payload_res.status_code == 200
    payload = payload_res.json()
    assert payload["task_id"] == task_id
    assert payload["message"] == "perform sorting task"

    # 7. Submit result
    submit_res = client.post(
        f"/cluster/hub/tasks/{task_id}/submit-result",
        json={"worker_id": "worker-abc", "result": "sorting result output data", "error": None}
    )
    assert submit_res.status_code == 200
    assert submit_res.json()["success"] is True

    # 8. Fetch execution result
    result_res = client.get(f"/cluster/hub/tasks/{task_id}/result")
    assert result_res.status_code == 200
    result_data = result_res.json()
    assert result_data["status"] == "completed"
    assert result_data["result"] == "sorting result output data"
    assert result_data["error"] is None

