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
    # Mock ask_model to return a structured JSON response
    mock_json = {
        "summary": "This paper presents a new method to reduce memory footprint by 40%.",
        "ideas": ["Use memory paging", "Compress model weights"],
        "usefulness_score": 85,
        "implementation_difficulty": 30
    }
    monkeypatch.setattr(
        "backend.core.research_agent.ask_model",
        lambda prompt, role, system=None: json.dumps(mock_json)
    )

    # 1. Clear database
    ResearchAgent.reset()
    assert len(ResearchAgent.list_results()) == 0

    # 2. Run analysis
    result = ResearchAgent.analyze_material(
        title="Optimizing LLM Inference Memory",
        content="We present an optimized layout where model weights are paged...",
        source_type="paper"
    )

    assert result["title"] == "Optimizing LLM Inference Memory"
    assert result["source_type"] == "paper"
    assert result["summary"] == mock_json["summary"]
    assert result["ideas"] == mock_json["ideas"]
    assert result["usefulness_score"] == 85
    assert result["implementation_difficulty"] == 30
    assert "id" in result

    # 3. Check persistent list
    stored_results = ResearchAgent.list_results()
    assert len(stored_results) == 1
    assert stored_results[0]["id"] == result["id"]


def test_research_agent_fallback_parsing(temp_research_db, monkeypatch):
    # Mock ask_model to return completely invalid JSON
    monkeypatch.setattr(
        "backend.core.research_agent.ask_model",
        lambda prompt, role, system=None: "This is completely non-JSON content from the LLM!"
    )

    ResearchAgent.reset()

    # 1. Run analysis - it should gracefully fall back
    result = ResearchAgent.analyze_material(
        title="Cool Blog Post",
        content="Short content explaining deep learning...",
        source_type="blog"
    )

    # Check fallbacks
    assert result["title"] == "Cool Blog Post"
    assert result["source_type"] == "blog"
    assert "Cool Blog Post" in result["summary"]
    assert len(result["ideas"]) == 1
    assert "Cool Blog Post" in result["ideas"][0]
    assert result["usefulness_score"] == 50
    assert result["implementation_difficulty"] == 50

    # Mock ask_model to return partial JSON (some missing fields or invalid format with markdown)
    mock_partial_markdown = "```json\n{\n  \"summary\": \"Parsed summary via regex\",\n  \"ideas\": [\"Parsed idea 1\"]\n}\n```"
    monkeypatch.setattr(
        "backend.core.research_agent.ask_model",
        lambda prompt, role, system=None: mock_partial_markdown
    )

    result2 = ResearchAgent.analyze_material(
        title="API Documentation",
        content="FastAPI is a modern web framework...",
        source_type="documentation"
    )

    assert result2["summary"] == "Parsed summary via regex"
    assert result2["ideas"] == ["Parsed idea 1"]
    assert result2["usefulness_score"] == 50
    assert result2["implementation_difficulty"] == 50


def test_research_agent_concurrency(temp_research_db, monkeypatch):
    # Setup mock LLM response
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

    # Launch multiple threads to write to the ledger concurrently
    threads = []
    def worker(idx):
        for i in range(10):
            ResearchAgent.analyze_material(
                title=f"Thread {idx} Paper {i}",
                content="Some content",
                source_type="paper"
            )

    for thread_idx in range(5):
        t = threading.Thread(target=worker, args=(thread_idx,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Verify that exactly 50 entries exist and they are all valid
    stored = ResearchAgent.list_results()
    assert len(stored) == 50
    assert len(set(x["id"] for x in stored)) == 50


def test_research_api_endpoints(temp_research_db, monkeypatch):
    client = TestClient(app)

    # Setup mock LLM response
    mock_json = {
        "summary": "API Test summary.",
        "ideas": ["API Idea"],
        "usefulness_score": 75,
        "implementation_difficulty": 25
    }
    monkeypatch.setattr(
        "backend.core.research_agent.ask_model",
        lambda prompt, role, system=None: json.dumps(mock_json)
    )

    ResearchAgent.reset()

    # 1. POST to analyze
    payload = {
        "title": "Ingested via API",
        "content": "This is a blog post talking about model caching.",
        "source_type": "blog"
    }
    response = client.post("/research/analyze", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["result"]["title"] == "Ingested via API"
    assert res_data["result"]["summary"] == "API Test summary."
    assert res_data["result"]["usefulness_score"] == 75
    assert res_data["result"]["implementation_difficulty"] == 25

    # 2. GET all results
    response_list = client.get("/research/results")
    assert response_list.status_code == 200
    list_data = response_list.json()
    assert len(list_data) == 1
    assert list_data[0]["title"] == "Ingested via API"
