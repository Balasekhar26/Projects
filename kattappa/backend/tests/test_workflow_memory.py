from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import load_config, BackendConfig
from backend.core.workflow_memory import WorkflowMemory


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
    monkeypatch.setattr("backend.core.workflow_memory.load_config", lambda: test_config)
    WorkflowMemory._schema_ensured = False
    yield test_db


def test_workflow_memory_save_and_retrieve():
    steps = [
        {"agent": "coder", "action": "WRITE_FILE", "success": True, "duration_ms": 1200},
        {"agent": "coder", "action": "RUN_TESTS", "success": False, "duration_ms": 5000, "rollback_executed": True, "rollback_success": True},
    ]

    WorkflowMemory.save_workflow_run(
        workflow_id="wf_123",
        goal="Compile the code",
        status="completed",
        success=True,
        total_duration_ms=6200,
        steps=steps,
    )

    run = WorkflowMemory.get_workflow_run("wf_123")
    assert run is not None
    assert run["goal"] == "Compile the code"
    assert run["success"] is True
    assert run["status"] == "completed"
    assert run["total_duration_ms"] == 6200
    assert len(run["steps"]) == 2
    assert run["steps"][0]["agent"] == "coder"
    assert run["steps"][0]["success"] is True
    assert run["steps"][1]["rollback_executed"] is True
    assert run["steps"][1]["rollback_success"] is True


def test_workflow_memory_not_found():
    assert WorkflowMemory.get_workflow_run("wf_nonexistent") is None


def test_workflow_memory_search():
    WorkflowMemory.save_workflow_run(
        workflow_id="wf_search_1",
        goal="Deploy static website to cloud storage",
        status="completed",
        success=True,
        total_duration_ms=1000,
        steps=[],
    )
    WorkflowMemory.save_workflow_run(
        workflow_id="wf_search_2",
        goal="Configure static storage settings",
        status="completed",
        success=True,
        total_duration_ms=2000,
        steps=[],
    )

    results = WorkflowMemory.search_workflows_by_goal("static")
    assert len(results) == 2
    assert {r["workflow_id"] for r in results} == {"wf_search_1", "wf_search_2"}


def test_workflow_memory_recent():
    for i in range(10):
        WorkflowMemory.save_workflow_run(
            workflow_id=f"wf_rec_{i}",
            goal=f"Task {i}",
            status="completed",
            success=True,
            total_duration_ms=100,
            steps=[],
        )

    recent = WorkflowMemory.get_recent_workflow_runs(limit=5)
    assert len(recent) == 5
    assert recent[0]["workflow_id"] == "wf_rec_9"


def test_workflow_memory_api():
    client = TestClient(app)
    response = client.post(
        "/cognitive/workflow/save",
        json={
            "workflow_id": "wf_api_1",
            "goal": "Test API pipeline",
            "status": "completed",
            "success": True,
            "total_duration_ms": 500,
            "steps": [{"agent": "browser", "action": "SEARCH_WEB", "success": True, "duration_ms": 500}],
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    search = client.get("/cognitive/workflow/search?q=API")
    assert search.status_code == 200
    assert len(search.json()["items"]) == 1
    assert search.json()["items"][0]["workflow_id"] == "wf_api_1"

    recent = client.get("/cognitive/workflow/recent?limit=2")
    assert recent.status_code == 200
    assert len(recent.json()["items"]) == 1
