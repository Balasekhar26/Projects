from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import load_config, BackendConfig
from backend.core.skill_graph import SkillGraph


@pytest.fixture(autouse=True)
def mock_db(tmp_path, monkeypatch):
    original_config = load_config()
    test_db = tmp_path / "kattappa_test.db"
    test_config = BackendConfig(
        root=original_config.root,
        backend_root=original_config.backend_root,
        ollama_host=original_config.ollama_host,
        model_map=original_config.model_map,
        chroma_path=original_config.chroma_path,
        sqlite_path=test_db,
        memory_collection=original_config.memory_collection,
        shell_enabled=original_config.shell_enabled,
        desktop_enabled=original_config.desktop_enabled,
        screen_capture_enabled=original_config.screen_capture_enabled,
        guidance_overlay_enabled=original_config.guidance_overlay_enabled,
        teach_mode_enabled=original_config.teach_mode_enabled,
        screenshots_dir=original_config.screenshots_dir,
        audio_dir=original_config.audio_dir,
        logs_dir=original_config.logs_dir,
        workspace_dir=original_config.workspace_dir,
        hardware_profile=original_config.hardware_profile,
        context_budget=original_config.context_budget,
    )
    monkeypatch.setattr("backend.core.config.load_config", lambda: test_config)
    monkeypatch.setattr("backend.core.knowledge_graph.load_config", lambda: test_config)
    from backend.core.knowledge_graph import KnowledgeGraph
    SkillGraph._schema_ensured = False
    KnowledgeGraph._schema_ensured = False
    yield test_db


def test_skill_graph_flow():
    # Register basic setup skill
    SkillGraph.register_skill(
        skill_id="setup_env",
        name="Setup Env",
        description="Prepares virtual env",
        tools=["create_directory", "write_file"],
        agents=["coder"],
    )

    # Register run test skill depending on setup env
    SkillGraph.register_skill(
        skill_id="run_test",
        name="Run Tests",
        description="Executes test runner",
        tools=["execute_command"],
        agents=["coder"],
        prerequisites=["setup_env"],
    )

    # 1. Verify detail mapping
    details = SkillGraph.get_skill_details("run_test")
    assert details is not None
    assert details["name"] == "Run Tests"
    assert "execute_command" in details["tools"]
    assert "coder" in details["agents"]
    assert "setup_env" in details["prerequisites"]

    # 2. Verify topological dependencies
    deps = SkillGraph.get_skill_dependencies("run_test")
    # setup_env should precede run_test because it's a prereq
    assert deps == ["setup_env", "run_test"]

    # 3. Find skills for tool
    skills = SkillGraph.find_skills_for_tool("write_file")
    assert "setup_env" in skills

    # 4. Verify prerequisite met
    assert SkillGraph.verify_skill_prerequisites_met("setup_env", ["create_directory", "write_file"]) is True
    assert SkillGraph.verify_skill_prerequisites_met("setup_env", ["create_directory"]) is False


def test_skill_graph_api():
    client = TestClient(app)

    # Register
    resp = client.post(
        "/cognitive/skill-graph/register",
        json={
            "skill_id": "api_skill",
            "name": "API Skill",
            "description": "API Test",
            "tools": ["tool_A"],
            "agents": ["coder"],
            "prerequisites": [],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Details
    det_resp = client.get("/cognitive/skill-graph/details/api_skill")
    assert det_resp.status_code == 200
    assert det_resp.json()["details"]["name"] == "API Skill"

    # Dependencies
    dep_resp = client.get("/cognitive/skill-graph/dependencies/api_skill")
    assert dep_resp.status_code == 200
    assert dep_resp.json()["dependencies"] == ["api_skill"]
