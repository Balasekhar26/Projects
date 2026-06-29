import pytest
import tempfile
import shutil
from pathlib import Path
from backend.core.workspace import WorkspaceManager


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_workspace_test_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    WorkspaceManager._schema_ensured = False

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_workspace_crud():
    # 1. Create a workspace
    w = WorkspaceManager.create_workspace(
        name="Research Lab",
        description="Workspace for scanning RF technology",
        project_ids=["p1", "p2"],
        goal_ids=["g1"],
        chat_session_id="session1"
    )
    assert w is not None
    assert w["name"] == "Research Lab"
    assert w["project_ids"] == ["p1", "p2"]
    assert w["goal_ids"] == ["g1"]
    assert w["chat_session_id"] == "session1"

    w_id = w["workspace_id"]

    # 2. Get workspace
    retrieved = WorkspaceManager.get_workspace(w_id)
    assert retrieved is not None
    assert retrieved["name"] == "Research Lab"

    # 3. Update workspace
    updated = WorkspaceManager.update_workspace(
        workspace_id=w_id,
        name="New Research Lab",
        project_ids=["p1", "p2", "p3"]
    )
    assert updated is not None
    assert updated["name"] == "New Research Lab"
    assert updated["project_ids"] == ["p1", "p2", "p3"]

    # 4. List workspaces
    w_list = WorkspaceManager.list_workspaces()
    assert len(w_list) == 1
    assert w_list[0]["workspace_id"] == w_id

    # 5. Delete workspace
    deleted = WorkspaceManager.delete_workspace(w_id)
    assert deleted is True

    # Confirm it is gone
    assert WorkspaceManager.get_workspace(w_id) is None


def test_workspace_api():
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)

    # 1. Create workspace
    response = client.post(
        "/workspaces",
        json={
            "name": "API Lab",
            "description": "testing api endpoints",
            "project_ids": ["p1"],
            "goal_ids": ["g1"]
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["workspace"]["name"] == "API Lab"
    w_id = data["workspace"]["workspace_id"]

    # 2. List workspaces
    response = client.get("/workspaces")
    assert response.status_code == 200
    assert len(response.json()["items"]) >= 1

    # 3. Get single workspace
    response = client.get(f"/workspaces/{w_id}")
    assert response.status_code == 200
    assert response.json()["workspace"]["name"] == "API Lab"

    # 4. Update workspace
    response = client.post(
        f"/workspaces/{w_id}",
        json={"name": "API Lab Updated"}
    )
    assert response.status_code == 200
    assert response.json()["workspace"]["name"] == "API Lab Updated"

    # 5. Delete workspace
    response = client.delete(f"/workspaces/{w_id}")
    assert response.status_code == 200
    assert response.json()["success"] is True

    # 6. Verify 404
    response = client.get(f"/workspaces/{w_id}")
    assert response.status_code == 404

