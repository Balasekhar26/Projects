from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import load_config, BackendConfig
from backend.core.curriculum_engine import CurriculumEngine


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
    monkeypatch.setattr("backend.core.curriculum_engine.load_config", lambda: test_config)
    CurriculumEngine._schema_ensured = False
    yield test_db


def test_curriculum_engine_flow():
    # Add challenge
    CurriculumEngine.add_challenge(
        challenge_id="ch_code_1",
        category="coding",
        title="Speed Compile",
        description="Compile within 2 seconds",
        success_criteria={"max_duration_ms": 2000, "min_success_rate": 0.8},
    )

    # Verify listing
    challenges = CurriculumEngine.list_challenges(category="coding")
    assert len(challenges) == 1
    assert challenges[0]["challenge_id"] == "ch_code_1"
    assert challenges[0]["status"] == "pending"

    # Run failed attempt due to duration exceed
    status = CurriculumEngine.update_challenge_attempt(
        challenge_id="ch_code_1",
        run_success=True,
        metrics={"duration_ms": 3000, "success_rate": 0.9},
    )
    assert status == "failed"

    # Run successful attempt satisfying criteria
    status = CurriculumEngine.update_challenge_attempt(
        challenge_id="ch_code_1",
        run_success=True,
        metrics={"duration_ms": 1500, "success_rate": 0.85},
    )
    assert status == "passed"


def test_curriculum_recommendations_with_low_performance(monkeypatch):
    # Register some challenges
    CurriculumEngine.add_challenge("ch_code", "coding", "Code Challenge", "...")
    CurriculumEngine.add_challenge("ch_mem", "memory", "Memory Challenge", "...")

    # Mock ActionMemory statistics to return low coder success rate
    class DummyStats:
        def to_dict(self):
            return {"total_actions": 10, "success_rate": 0.4}

    class DummyActionMemory:
        @staticmethod
        def get_agent_statistics(agent: str):
            if agent == "coder":
                return DummyStats()
            # Other agents have high success rate
            class HighStats:
                def to_dict(self):
                    return {"total_actions": 10, "success_rate": 0.9}
            return HighStats()

    monkeypatch.setattr("backend.core.action_memory.ActionMemory", DummyActionMemory)

    # Recommends should suggest coding category challenges first due to low success stats
    recs = CurriculumEngine.get_recommended_challenges()
    assert len(recs) == 1
    assert recs[0]["category"] == "coding"


def test_curriculum_api():
    client = TestClient(app)

    # Create challenge
    resp = client.post(
        "/cognitive/curriculum/challenge",
        json={
            "challenge_id": "ch_api",
            "category": "safety",
            "title": "API Challenge",
            "description": "API Test",
            "success_criteria": {"min_success_rate": 1.0},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # List challenges
    list_resp = client.get("/cognitive/curriculum/challenges?category=safety")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["challenges"]) == 1

    # Recommendations
    rec_resp = client.get("/cognitive/curriculum/recommendations")
    assert rec_resp.status_code == 200
    assert len(rec_resp.json()["recommendations"]) > 0
