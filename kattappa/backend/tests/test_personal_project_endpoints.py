import pytest
import tempfile
import shutil
import time
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.goal_memory import GoalMemory
from backend.core.goal_manager import GoalManager
from backend.core.project_memory import ProjectMemory


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_ppm_endpoints_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    GoalMemory._schema_ensured = False
    ProjectMemory._schema_ensured = False
    GoalMemory.reset()
    ProjectMemory.reset()

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_ppm_lifecycle_endpoints():
    client = TestClient(app, raise_server_exceptions=True)

    # 1. Add originating goal
    goal = GoalManager.add_goal(title="End-to-End PPM Goal", current_state="IDEA")
    g_id = goal["goal_id"]

    # 2. Create project linked to goal
    response_proj = client.post(
        "/api/ppm/projects",
        json={"linked_goal_id": g_id, "title": "API Project", "description": "Endpoints test project", "original_scope": "API Test Scope"}
    )
    assert response_proj.status_code == 200
    proj = response_proj.json()["item"]
    p_id = proj["project_id"]
    assert proj["title"] == "API Project"
    assert proj["status"] == "PROPOSED"

    # 3. Create milestone
    response_mil = client.post(
        "/api/ppm/milestones",
        json={"project_id": p_id, "title": "Milestone A", "weight": 2.0}
    )
    assert response_mil.status_code == 200
    mil = response_mil.json()["item"]
    m_id = mil["milestone_id"]
    assert mil["title"] == "Milestone A"

    # 4. Create task
    response_task = client.post(
        "/api/ppm/tasks",
        json={"milestone_id": m_id, "title": "Task A", "description": "Write code", "effort_score": 3}
    )
    assert response_task.status_code == 200
    task = response_task.json()["item"]
    t_id = task["task_id"]
    assert task["title"] == "Task A"

    # 5. Allocate & consume resources
    alloc_resp = client.post(
        "/api/ppm/resources",
        json={"project_id": p_id, "resource_type": "time_hours", "allocated": 50.0}
    )
    assert alloc_resp.status_code == 200
    assert alloc_resp.json()["item"]["allocated"] == 50.0

    consume_resp = client.post(
        "/api/ppm/resources/consume",
        json={"project_id": p_id, "resource_type": "time_hours", "amount": 10.0}
    )
    assert consume_resp.status_code == 200
    assert consume_resp.json()["item"]["remaining_amount"] == 40.0

    # Exhaust resource and check 400 validation error
    consume_exhaust = client.post(
        "/api/ppm/resources/consume",
        json={"project_id": p_id, "resource_type": "time_hours", "amount": 45.0}
    )
    assert consume_exhaust.status_code == 400
    assert "Resource exhaustion" in consume_exhaust.json()["detail"]

    # 6. Raise blocker
    blocker_resp = client.post(
        "/api/ppm/blockers",
        json={"project_id": p_id, "severity": "blocking", "source": "Missing API keys"}
    )
    assert blocker_resp.status_code == 200
    blocker_id = blocker_resp.json()["item"]["blocker_id"]

    # Verify project health degraded on get
    get_proj = client.get(f"/api/ppm/projects/{p_id}")
    assert get_proj.status_code == 200
    assert get_proj.json()["item"]["health_status"] == "CRITICAL"

    # Resolve blocker
    resolve_resp = client.post(f"/api/ppm/blockers/{blocker_id}/resolve")
    assert resolve_resp.status_code == 200

    # Verify health restored
    get_proj = client.get(f"/api/ppm/projects/{p_id}")
    assert get_proj.json()["item"]["health_status"] in {"GOOD", "EXCELLENT"}

    # 7. Log revisions
    rev_resp = client.post(
        f"/api/ppm/projects/{p_id}/revisions",
        json={"author": "API client", "summary": "PPM endpoints successfully verified"}
    )
    assert rev_resp.status_code == 200

    # 8. Retrieve project report
    report_resp = client.get(f"/api/ppm/projects/{p_id}/report")
    assert report_resp.status_code == 200
    assert "insights" in report_resp.json()["report"]

    # 9. Complete project verification checks
    comp_fail = client.post(
        f"/api/ppm/projects/{p_id}/complete",
        json={"validator": None, "user_confirmed": False}
    )
    assert comp_fail.status_code == 400
    assert "Project completion validation failed" in comp_fail.json()["detail"]

    comp_success = client.post(
        f"/api/ppm/projects/{p_id}/complete",
        json={"validator": "API validator suite"}
    )
    assert comp_success.status_code == 200
    assert comp_success.json()["item"]["status"] == "COMPLETED"
