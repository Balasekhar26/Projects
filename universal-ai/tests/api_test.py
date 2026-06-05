from fastapi.testclient import TestClient

from ai_system.api.server import app


def test_status_api() -> None:
    client = TestClient(app)
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "AI_System"
    assert "models" in data
