import pytest
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.goal_memory import GoalMemory
from backend.core.goal_manager import GoalManager

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_human_goals_endpoints_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    GoalMemory._schema_ensured = False
    GoalMemory.reset()

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_absolute_policies_endpoint():
    client = TestClient(app)
    response = client.get("/api/goals/policies/absolute")
    assert response.status_code == 200
    data = response.json()
    assert "policies" in data
    assert len(data["policies"]) == 2
    assert data["policies"][0]["policy_id"] == "ABS-POL-CORE-SHIELD"


def test_update_goal_endpoint_and_drift():
    client = TestClient(app)
    # Create cognitive goal
    goal = GoalManager.add_goal(
        title="Cache refactoring",
        description="Verify redis tokens.",
        importance_score=70.0,
    )
    g_id = goal["goal_id"]

    # Update goal content via API
    update_response = client.post(
        f"/api/goals/{g_id}/update",
        json={"title": "Cache refactoring v2", "description": "Verify redis tokens and check limits."}
    )
    assert update_response.status_code == 200
    updated_goal = update_response.json()["item"]
    assert len(updated_goal["metadata"]["revisions"]) == 1

    # Drift the goal significantly
    drift_response = client.post(
        f"/api/goals/{g_id}/update",
        json={"title": "Plant greenhouse seeds", "description": "Grow organic tomatoes and cucumbers."}
    )
    assert drift_response.status_code == 200
    drifted_goal = drift_response.json()["item"]
    assert drifted_goal["status"] == "CONFLICTED"
    assert drifted_goal["current_state"] == "STALE_CONTEXT"


def test_complete_goal_validation_endpoint():
    client = TestClient(app)
    # 1. Cognitive goal complete validation
    goal = GoalManager.add_goal(
        title="Cognitive validation task",
        importance_score=80.0,
        current_state="ACTIVE",
    )
    g_id = goal["goal_id"]

    # Try to complete without parameters -> should fail (400 code)
    response = client.post(f"/api/goals/{g_id}/complete")
    assert response.status_code == 400
    assert "Completion validation failed" in response.json()["detail"]

    # Complete with validator via JSON body
    response_val = client.post(
        f"/api/goals/{g_id}/complete",
        json={"validator": "Playwright integration tests"}
    )
    assert response_val.status_code == 200
    assert response_val.json()["item"]["status"] == "COMPLETED"

    # 2. Legacy goal complete validation (non-cognitive)
    GoalMemory.reset()
    legacy_goal = GoalManager.add_goal(
        title="Spelling correction",
    )
    # Start it
    client.post(f"/api/goals/{legacy_goal['goal_id']}/start")
    
    # Complete without body should succeed for legacy goal
    response_legacy = client.post(f"/api/goals/{legacy_goal['goal_id']}/complete")
    assert response_legacy.status_code == 200
    assert response_legacy.json()["item"]["status"] == "COMPLETED"
