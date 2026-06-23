from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import load_config, BackendConfig
from backend.core.long_term_goal_engine import LongTermGoalEngine
from backend.core.project_manager import ProjectManager


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
    monkeypatch.setattr("backend.core.long_term_goal_engine.load_config", lambda: test_config)
    monkeypatch.setattr("backend.core.project_manager.load_config", lambda: test_config)
    LongTermGoalEngine._schema_ensured = False
    ProjectManager._schema_ensured = False
    yield test_db


def test_long_term_goal_hierarchy_preconditions_and_success(mock_db, tmp_path):
    # 1. Register parent goal
    LongTermGoalEngine.register_goal(
        goal_id="goal_parent",
        title="Establish Colony",
        description="Establish baseline colony",
        preconditions={"colony_ready": True},
        success_criteria={"file_exists": "colony_config.json"},
    )

    # 2. Register child goal
    LongTermGoalEngine.register_goal(
        goal_id="goal_child",
        title="Setup Communications",
        description="Configure radio satellites",
        parent_id="goal_parent",
    )

    # Verify hierarchical tree
    tree = LongTermGoalEngine.get_goal_hierarchy()
    assert len(tree) == 1
    assert tree[0]["goal_id"] == "goal_parent"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["goal_id"] == "goal_child"

    # Evaluate preconditions
    # Check false when not matching context
    assert LongTermGoalEngine.evaluate_preconditions("goal_parent", {"colony_ready": False}) is False
    assert LongTermGoalEngine.evaluate_preconditions("goal_parent", {"colony_ready": True}) is True

    # Evaluate blackboard precondition check
    LongTermGoalEngine.register_goal(
        goal_id="goal_bb",
        title="Blackboard Precondition",
        description="Requires blackboard key",
        preconditions={"blackboard_key_present": "auth_token"},
    )
    # Checks false because blackboard variable is not written yet
    assert LongTermGoalEngine.evaluate_preconditions("goal_bb", {"project_name": "orbit"}) is False

    ProjectManager.write_to_blackboard("orbit", "auth_token", "xyz_session")
    assert LongTermGoalEngine.evaluate_preconditions("goal_bb", {"project_name": "orbit"}) is True

    # Evaluate success criteria (file_exists check)
    assert LongTermGoalEngine.check_goal_success("goal_parent", {"workspace_dir": str(tmp_path)}) is False

    # Create target file to trigger success validation passing
    target_file = tmp_path / "colony_config.json"
    target_file.write_text("{}", encoding="utf-8")
    assert LongTermGoalEngine.check_goal_success("goal_parent", {"workspace_dir": str(tmp_path)}) is True


def test_long_term_goal_api():
    client = TestClient(app)

    # Register
    resp = client.post(
        "/cognitive/long-term-goals/register",
        json={
            "goal_id": "api_goal",
            "title": "API Goal",
            "description": "API Test",
            "preconditions": {},
            "success_criteria": {},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Hierarchy
    get_resp = client.get("/cognitive/long-term-goals/hierarchy")
    assert get_resp.status_code == 200
    assert len(get_resp.json()["hierarchy"]) == 1
    assert get_resp.json()["hierarchy"][0]["goal_id"] == "api_goal"
