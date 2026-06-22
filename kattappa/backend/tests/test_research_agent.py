from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.research_agent import ResearchAgent


@pytest.fixture
def temp_research_db(monkeypatch):
    """Sets a temporary folder for research results database."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_research_test_")
    monkeypatch.setattr("backend.core.research_agent.runtime_data_root", lambda: Path(temp_dir))
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_research_agent_analysis_and_persistence(temp_research_db, monkeypatch):
    # Mock ask_model to return a structured JSON response matching the revised schema
    mock_json = {
        "summary": "This paper presents a new method to reduce memory footprint by 40%.",
        "ideas": ["Use memory paging", "Compress model weights"],
        "usefulness_score": 85,
        "implementation_difficulty": 30,
        "comparison": {
            "existing_capability": "Standard caching pipeline",
            "missing_capability": "Dynamic memory layouts",
            "evidence_strength": "High (tested across 3 benchmarks)",
            "risks": "Slight latency overhead during cold loads",
            "touches_protected_core": False
        },
        "claims": [
            {
                "claim": "Weight compression saves 40% memory",
                "source_type": "peer_reviewed",
                "verification": "unverified"
            }
        ]
    }
    monkeypatch.setattr(
        "backend.core.research_agent.ask_model",
        lambda prompt, role, system=None: json.dumps(mock_json)
    )

    # 1. Clear database
    ResearchAgent.reset()
    assert len(ResearchAgent.list_results()) == 0

    # 2. Run analysis for peer_reviewed source
    result = ResearchAgent.analyze_material(
        title="Optimizing LLM Inference Memory",
        content="We present an optimized layout where model weights are paged...",
        source_type="peer_reviewed"
    )

    assert result["title"] == "Optimizing LLM Inference Memory"
    assert result["source_type"] == "peer_reviewed"
    assert result["trust_level"] == "Medium"
    assert result["summary"] == mock_json["summary"]
    assert result["ideas"] == mock_json["ideas"]
    assert result["usefulness_score"] == 85
    assert result["implementation_difficulty"] == 30
    
    # Verify comparison block
    comp = result["comparison"]
    assert comp["existing_capability"] == "Standard caching pipeline"
    assert comp["touches_protected_core"] is False

    # Verify claims list
    assert len(result["claims"]) == 1
    assert result["claims"][0]["claim"] == "Weight compression saves 40% memory"
    assert result["claims"][0]["verification"] == "unverified"


def test_research_agent_social_exclusions_and_trust(temp_research_db, monkeypatch):
    ResearchAgent.reset()

    # 1. Verify social posts raise ValueError
    with pytest.raises(ValueError) as excinfo:
        ResearchAgent.analyze_material(
            title="Cool tweet",
            content="Check this out! LLM speedup by 10x!",
            source_type="social_post"
        )
    assert "social posts are ignored" in str(excinfo.value).lower()

    # 2. Verify trust level mappings for other sources
    mock_json = {
        "summary": "Sample summary",
        "ideas": ["Sample idea"],
        "usefulness_score": 60,
        "implementation_difficulty": 40,
        "comparison": {
            "existing_capability": "None",
            "missing_capability": "None",
            "evidence_strength": "Low",
            "risks": "None",
            "touches_protected_core": False
        },
        "claims": []
    }
    monkeypatch.setattr(
        "backend.core.research_agent.ask_model",
        lambda prompt, role, system=None: json.dumps(mock_json)
    )

    # Reproduced
    r1 = ResearchAgent.analyze_material("Title 1", "Content 1", "reproduced")
    assert r1["trust_level"] == "High"
    assert r1["source_type"] == "reproduced"

    # Preprint
    r2 = ResearchAgent.analyze_material("Title 2", "Content 2", "preprint")
    assert r2["trust_level"] == "Low"

    # Blog
    r3 = ResearchAgent.analyze_material("Title 3", "Content 3", "engineering_blog")
    assert r3["trust_level"] == "Very Low"


def test_research_agent_protected_core_touches(temp_research_db, monkeypatch):
    # Mock ask_model
    mock_json = {
        "summary": "Sample summary",
        "ideas": ["Sample idea"],
        "usefulness_score": 60,
        "implementation_difficulty": 40,
        "comparison": {
            "existing_capability": "None",
            "missing_capability": "None",
            "evidence_strength": "Low",
            "risks": "None",
            "touches_protected_core": False
        },
        "claims": []
    }
    monkeypatch.setattr(
        "backend.core.research_agent.ask_model",
        lambda prompt, role, system=None: json.dumps(mock_json)
    )

    ResearchAgent.reset()

    # 1. Analyze safe content
    r_safe = ResearchAgent.analyze_material("Safe Paper", "This discusses basic data parsing algorithms.", "peer_reviewed")
    assert r_safe["comparison"]["touches_protected_core"] is False

    # 2. Analyze content touching protected core (keywords trigger local check)
    r_unsafe = ResearchAgent.analyze_material("Dangerous Paper", "We propose replacing the validators in the policy_engine.", "peer_reviewed")
    assert r_unsafe["comparison"]["touches_protected_core"] is True


def test_research_agent_concurrency(temp_research_db, monkeypatch):
    mock_json = {
        "summary": "Concurrent execution test summary.",
        "ideas": ["Concurrency Idea"],
        "usefulness_score": 90,
        "implementation_difficulty": 10
    }
    monkeypatch.setattr(
        "backend.core.research_agent.ask_model",
        lambda prompt, role, system=None: json.dumps(mock_json)
    )

    ResearchAgent.reset()

    threads = []
    def worker(idx):
        for i in range(5):
            ResearchAgent.analyze_material(
                title=f"Thread {idx} Paper {i}",
                content="Some content",
                source_type="preprint"
            )

    for thread_idx in range(5):
        t = threading.Thread(target=worker, args=(thread_idx,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    stored = ResearchAgent.list_results()
    assert len(stored) == 25
    assert all(x["trust_level"] == "Low" for x in stored)


def test_research_api_endpoints(temp_research_db, monkeypatch):
    client = TestClient(app)

    mock_json = {
        "summary": "API Test summary.",
        "ideas": ["API Idea"],
        "usefulness_score": 75,
        "implementation_difficulty": 25,
        "comparison": {
            "existing_capability": "Yes",
            "missing_capability": "No",
            "evidence_strength": "Medium",
            "risks": "Low",
            "touches_protected_core": False
        },
        "claims": []
    }
    monkeypatch.setattr(
        "backend.core.research_agent.ask_model",
        lambda prompt, role, system=None: json.dumps(mock_json)
    )

    ResearchAgent.reset()

    # 1. POST to analyze social_post (should return 400)
    payload_social = {
        "title": "Unsafe tweet",
        "content": "Look at my cool hack",
        "source_type": "social_post"
    }
    response_social = client.post("/research/analyze", json=payload_social)
    assert response_social.status_code == 400
    assert "social posts are ignored" in response_social.json()["detail"].lower()

    # 2. POST to analyze reproduced paper (should return 200)
    payload_valid = {
        "title": "Ingested via API",
        "content": "This is a reproduced paper about model caching.",
        "source_type": "reproduced"
    }
    response_valid = client.post("/research/analyze", json=payload_valid)
    assert response_valid.status_code == 200
    res_data = response_valid.json()
    assert res_data["status"] == "success"
    assert res_data["result"]["trust_level"] == "High"
    assert res_data["result"]["comparison"]["touches_protected_core"] is False

    # 3. GET all results
    response_list = client.get("/research/results")
    assert response_list.status_code == 200
    list_data = response_list.json()
    assert len(list_data) == 1
    assert list_data[0]["title"] == "Ingested via API"
