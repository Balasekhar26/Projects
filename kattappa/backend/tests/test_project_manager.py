from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import load_config, BackendConfig
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
    monkeypatch.setattr("backend.core.project_manager.load_config", lambda: test_config)
    ProjectManager._schema_ensured = False
    yield test_db


def test_project_manager_task_dependencies_flow():
    # 1. Create a parent task and child task depending on parent
    ProjectManager.create_project_task(
        task_id="task_parent",
        project_name="suit_upgrade",
        title="Analyze thrusters",
        assigned_agent="researcher",
        dependencies=[],
    )

    ProjectManager.create_project_task(
        task_id="task_child",
        project_name="suit_upgrade",
        title="Calibrate alignment",
        assigned_agent="coder",
        dependencies=["task_parent"],
    )

    # Verify initial states: parent is ready, child is blocked
    tasks = ProjectManager.get_project_tasks("suit_upgrade")
    by_id = {t["task_id"]: t for t in tasks}
    assert by_id["task_parent"]["status"] == "ready"
    assert by_id["task_child"]["status"] == "blocked"

    # Start and complete the parent task
    ProjectManager.update_task_state("task_parent", "completed")

    # Verify that child task was automatically updated to 'ready' because its dependency parent completed
    tasks_after = ProjectManager.get_project_tasks("suit_upgrade")
    by_id_after = {t["task_id"]: t for t in tasks_after}
    assert by_id_after["task_child"]["status"] == "ready"


def test_project_manager_blackboard():
    ProjectManager.write_to_blackboard("suit_upgrade", "thruster_level", 95.5)
    val = ProjectManager.read_from_blackboard("suit_upgrade", "thruster_level")
    assert val == 95.5

    # Non-existent key
    assert ProjectManager.read_from_blackboard("suit_upgrade", "non_existent") is None


def test_project_manager_api():
    client = TestClient(app)

    # Create task
    resp = client.post(
        "/cognitive/project-manager/task",
        json={
            "task_id": "api_task",
            "project_name": "api_project",
            "title": "API Task",
            "assigned_agent": "browser",
            "dependencies": [],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Query tasks
    get_resp = client.get("/cognitive/project-manager/tasks/api_project")
    assert get_resp.status_code == 200
    assert len(get_resp.json()["tasks"]) == 1
    assert get_resp.json()["tasks"][0]["task_id"] == "api_task"

    # Write blackboard
    bb_resp = client.post(
        "/cognitive/project-manager/blackboard",
        json={"project_name": "api_project", "key": "status_flag", "value": "green"},
    )
    assert bb_resp.status_code == 200
    assert bb_resp.json()["status"] == "ok"
