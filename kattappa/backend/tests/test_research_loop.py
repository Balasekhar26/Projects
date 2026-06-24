from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.research_loop import ResearchLoop


@pytest.fixture(autouse=True)
def isolated_research_loop(tmp_path, monkeypatch):
    # Mock config to use isolated db
    from backend.core.config import BackendConfig
    import backend.core.config as config_module
    
    test_db = tmp_path / "kattappa_research_test.db"
    
    mock_config = BackendConfig(
        root=tmp_path,
        backend_root=tmp_path,
        ollama_host="http://127.0.0.1:11434",
        model_map={},
        chroma_path=tmp_path / "chroma",
        sqlite_path=test_db,
        memory_collection="kattappa_memory",
        shell_enabled=False,
        desktop_enabled=True,
        screen_capture_enabled=False,
        guidance_overlay_enabled=True,
        teach_mode_enabled=True,
        screenshots_dir=tmp_path / "screenshots",
        audio_dir=tmp_path / "audio",
        logs_dir=tmp_path / "logs",
        workspace_dir=tmp_path / "workspace",
        hardware_profile="BALANCED",
        context_budget=4096,
    )
    
    monkeypatch.setattr(config_module, "load_config", lambda: mock_config)
    ResearchLoop.reset()
    yield
    ResearchLoop.reset()


def test_verify_citation():
    # Valid arXiv IDs
    assert ResearchLoop.verify_citation("arXiv:1706.03762v1", None) is True
    assert ResearchLoop.verify_citation("1706.03762", None) is True
    assert ResearchLoop.verify_citation("arXiv:2012.12345v3", None) is True
    assert ResearchLoop.verify_citation("2012.12345", None) is True

    # Valid DOIs
    assert ResearchLoop.verify_citation(None, "10.1000/xyz123") is True
    assert ResearchLoop.verify_citation(None, "10.1145/3318464.3389700") is True

    # Invalid arXiv IDs
    assert ResearchLoop.verify_citation("arXiv:invalid", None) is False
    assert ResearchLoop.verify_citation("1706.abc", None) is False

    # Invalid DOIs
    assert ResearchLoop.verify_citation(None, "invalid/doi") is False
    assert ResearchLoop.verify_citation(None, "10/1000/xyz123") is False

    # Empty inputs
    assert ResearchLoop.verify_citation(None, None) is False
    assert ResearchLoop.verify_citation("", "") is False


def test_calculate_priority():
    # Score calculation checks
    # Formula: 0.3 * relevance + 0.25 * reproducibility + 0.25 * expected_gain + 0.2 * evidence_strength
    
    # All 10s should result in 10.0
    score = ResearchLoop.calculate_priority(10.0, 10.0, 10.0, 10.0)
    assert score == 10.0

    # Middle scores
    score = ResearchLoop.calculate_priority(8.0, 7.0, 9.0, 6.0)
    # 0.3*8 + 0.25*7 + 0.25*9 + 0.2*6 = 2.4 + 1.75 + 2.25 + 1.2 = 7.6
    assert score == 7.60

    # Out of bounds clamping
    score = ResearchLoop.calculate_priority(12.0, -1.0, 15.0, 5.0)
    # Clamp to: 10.0, 0.0, 10.0, 5.0
    # 0.3*10 + 0.25*0 + 0.25*10 + 0.2*5 = 3.0 + 0.0 + 2.5 + 1.0 = 6.5
    assert score == 6.5


def test_ingest_paper_verified_and_high_priority():
    claims = [
        {
            "claim_text": "ActiveMem style compressed memory yields 15% better recall",
            "target_component": "human_memory",
            "expected_delta": 0.15,
            "arena_suite_id": "mem_recall_suite"
        }
    ]
    
    metrics = {
        "relevance": 9.5,
        "reproducibility": 9.0,
        "expected_gain": 9.5,
        "evidence_strength": 9.0
    }
    # Score: 0.3*9.5 + 0.25*9.0 + 0.25*9.5 + 0.2*9.0 = 2.85 + 2.25 + 2.375 + 1.8 = 9.275 -> 9.28
    
    res = ResearchLoop.ingest_paper(
        title="ActiveMem: Distributed Active Memory for LLMs",
        authors="John Doe, Jane Smith",
        arxiv_id="arXiv:2305.12345v1",
        doi=None,
        published_date="2023-05-15",
        claims=claims,
        metrics=metrics
    )
    
    assert res["verification_status"] == "verified"
    assert res["priority_score"] == 9.28
    assert res["experiment_candidate"] is True
    assert len(res["experiment_ids"]) == 1
    assert len(res["proposal_ids"]) == 1


def test_ingest_paper_unverified_and_low_priority():
    claims = [
        {
            "claim_text": "SpatialWorld reasoning increases spatial ability",
            "target_component": "spatial_reasoning",
            "expected_delta": 0.05,
            "arena_suite_id": "spatial_suite"
        }
    ]
    
    metrics = {
        "relevance": 5.0,
        "reproducibility": 6.0,
        "expected_gain": 4.0,
        "evidence_strength": 5.0
    }
    # Score: 0.3*5 + 0.25*6 + 0.25*4 + 0.2*5 = 1.5 + 1.5 + 1.0 + 1.0 = 5.0
    
    res = ResearchLoop.ingest_paper(
        title="SpatialWorld: Benchmarking spatial reasoning",
        authors="Alice Cooper",
        arxiv_id="invalid-arxiv-id",
        doi=None,
        published_date="2024-01-10",
        claims=claims,
        metrics=metrics
    )
    
    assert res["verification_status"] == "rejected"
    assert res["priority_score"] == 5.0
    assert res["experiment_candidate"] is False
    assert len(res["experiment_ids"]) == 1
    assert len(res["proposal_ids"]) == 0  # score <= 8.5, so no proposal


def test_list_proposals():
    # Ingest a high priority paper
    claims = [
        {
            "claim_text": "ActiveMem recall boost",
            "target_component": "human_memory",
            "expected_delta": 0.15,
            "arena_suite_id": "mem_recall_suite"
        }
    ]
    metrics = {
        "relevance": 9.5,
        "reproducibility": 9.0,
        "expected_gain": 9.5,
        "evidence_strength": 9.0
    }
    ResearchLoop.ingest_paper(
        title="ActiveMem: Distributed Active Memory for LLMs",
        authors="John Doe, Jane Smith",
        arxiv_id="arXiv:2305.12345v1",
        doi=None,
        published_date="2023-05-15",
        claims=claims,
        metrics=metrics
    )
    
    proposals = ResearchLoop.list_proposals()
    assert len(proposals) == 1
    prop = proposals[0]
    assert prop["title"] == "ActiveMem: Distributed Active Memory for LLMs"
    assert prop["claim_text"] == "ActiveMem recall boost"
    assert prop["target_component"] == "human_memory"
    assert prop["roi_score"] == 9.28
    assert prop["proposal_status"] == "pending"


def test_evaluate_experiment_candidate():
    claims = [
        {
            "claim_text": "ActiveMem recall boost",
            "target_component": "human_memory",
            "expected_delta": 0.15,
            "arena_suite_id": "mem_recall_suite"
        }
    ]
    metrics = {
        "relevance": 9.5,
        "reproducibility": 9.0,
        "expected_gain": 9.5,
        "evidence_strength": 9.0
    }
    res = ResearchLoop.ingest_paper(
        title="ActiveMem: Distributed Active Memory for LLMs",
        authors="John Doe, Jane Smith",
        arxiv_id="arXiv:2305.12345v1",
        doi=None,
        published_date="2023-05-15",
        claims=claims,
        metrics=metrics
    )
    
    exp_id = res["experiment_ids"][0]
    
    # Evaluate with success = True
    eval_res = ResearchLoop.evaluate_experiment_candidate(exp_id, {"success": True, "delta": 0.18})
    assert eval_res["status"] == "verified"
    
    # Verify DB update in proposals list
    proposals = ResearchLoop.list_proposals()
    assert proposals[0]["proposal_status"] == "verified"
    assert proposals[0]["experiment_status"] == "verified"


def test_api_endpoints():
    client = TestClient(app)
    
    # 1. Ingest paper via API
    payload = {
        "title": "Deployment-Time Memorization in Foundation-Model Agents",
        "authors": "Jane Doe, Bob Johnson",
        "arxiv_id": "arXiv:2606.12345v1",
        "doi": None,
        "published_date": "2026-06-01",
        "claims": [
            {
                "claim_text": "Deployment-time memory metrics help audit privacy",
                "target_component": "memory_safety",
                "expected_delta": 0.25,
                "arena_suite_id": "privacy_suite"
            }
        ],
        "metrics": {
            "relevance": 9.5,
            "reproducibility": 9.5,
            "expected_gain": 9.0,
            "evidence_strength": 9.5
        }
    }
    
    # Score: 0.3*9.5 + 0.25*9.5 + 0.25*9.0 + 0.2*9.5 = 2.85 + 2.375 + 2.25 + 1.9 = 9.375 -> 9.38
    resp = client.post("/research/ingest", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["verification_status"] == "verified"
    assert res_data["priority_score"] == 9.38
    assert res_data["experiment_candidate"] is True
    assert len(res_data["experiment_ids"]) == 1
    assert len(res_data["proposal_ids"]) == 1
    
    exp_id = res_data["experiment_ids"][0]
    
    # 2. Get proposals via API
    resp = client.get("/research/proposals")
    assert resp.status_code == 200
    proposals = resp.json()
    assert len(proposals) == 1
    assert proposals[0]["title"] == "Deployment-Time Memorization in Foundation-Model Agents"
    
    # 3. Evaluate experiment candidate via API
    eval_payload = {
        "experiment_id": exp_id,
        "run_results": {
            "success": True,
            "notes": "Verified privacy audit metrics"
        }
    }
    resp = client.post("/research/evaluate", json=eval_payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "verified"
    
    # 4. Check status update in proposals
    resp = client.get("/research/proposals")
    assert resp.status_code == 200
    assert resp.json()[0]["proposal_status"] == "verified"
