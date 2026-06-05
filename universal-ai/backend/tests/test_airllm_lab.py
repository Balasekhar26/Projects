from fastapi.testclient import TestClient

from backend.labs.airllm_lab.adapter import airllm_status
from backend.main import app


def test_airllm_status_is_optional_lab() -> None:
    status = airllm_status()
    assert status["key"] == "airllm"
    assert status["runtime"] == "optional_experimental"
    assert "not chat speed" in status["speed_note"]
    assert "airllm" in status["imports"]


def test_airllm_status_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/ai-engine/airllm/status")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "AirLLM Huge Model Lab"
    assert data["ready"] is (data["imports"]["airllm"] and data["imports"]["torch"])


def test_airllm_generate_fails_cleanly_when_missing_or_invalid() -> None:
    client = TestClient(app)
    response = client.post(
        "/ai-engine/airllm/generate",
        json={"prompt": "", "max_new_tokens": 80, "compression": "4bit"},
    )
    assert response.status_code == 400
    assert "prompt is required" in response.json()["detail"]

