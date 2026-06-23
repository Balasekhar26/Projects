from __future__ import annotations

import os
import shutil
import tempfile
import json
import pytest
from pathlib import Path

from backend.agents.browser import browser_node
from backend.agents.desktop import desktop_node
from backend.agents.coder import coder_node
from backend.agents.researcher import researcher_node
from backend.agents.file_agent import file_node
from backend.agents.voice import voice_node
from backend.agents.monitoring import monitoring_node, MonitoringAgent
from backend.core.state import AgentState


@pytest.fixture
def mock_env(monkeypatch):
    """Sets a temporary folder for reputations and memory databases."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_tool_universe_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_coder_safety_boundary(mock_env):
    """Tests that Code Agent blocks direct modifications of protected core files."""
    state: AgentState = {
        "user_input": "Modify backend/core/proposal_engine.py to bypass Occam Gate",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
    }
    res = coder_node(state)
    assert "strictly prohibited" in res["result"].lower()
    assert any("blocked" in log.lower() for log in res["logs"])


def test_coder_ast_syntax_checker(mock_env):
    """Tests Code Agent AST syntax verification."""
    temp_file = mock_env / "dummy_test.py"
    temp_file.write_text("def test():\n    print('hello')", encoding="utf-8")
    
    state: AgentState = {
        "user_input": f"Check the AST syntax of {temp_file}",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
    }
    res = coder_node(state)
    assert "PASSED" in res["result"]
    assert any("validated syntax" in log for log in res["logs"])

    # Test invalid syntax
    temp_file.write_text("def test(\n    print('hello')", encoding="utf-8")
    res = coder_node(state)
    assert "FAILED" in res["result"]


def test_desktop_safety_boundary(mock_env):
    """Tests that Desktop Agent blocks access or actions referencing protected core files."""
    state: AgentState = {
        "user_input": "Open the safety.py file in text editor and change it",
        "plan": None,
        "selected_agent": "desktop",
        "logs": [],
        "result": None,
    }
    res = desktop_node(state)
    assert "strictly prohibited" in res["result"].lower()
    assert any("blocked" in log for log in res["logs"])


def test_desktop_simulation_mode(mock_env):
    """Tests that Desktop Agent runs in simulation mode when KATTAPPA_ENV=test."""
    state: AgentState = {
        "user_input": "Open web browser and open Excel",
        "plan": None,
        "selected_agent": "desktop",
        "logs": [],
        "result": None,
    }
    res = desktop_node(state)
    assert "Simulated desktop action successfully executed" in res["result"]
    assert any("simulated" in log.lower() for log in res["logs"])


def test_browser_read_only_and_approval_gates(mock_env):
    """Tests that Browser Agent enforces read-only defaults and form/purchase gates."""
    # Write trigger: submit form
    state: AgentState = {
        "user_input": "Go to AWS console and submit the instance form",
        "plan": None,
        "selected_agent": "browser",
        "logs": [],
        "result": None,
    }
    res = browser_node(state)
    assert res["approval_required"] is True
    assert "human review" in res["result"].lower()


    # Read action: search
    state_read: AgentState = {
        "user_input": "What is the capital of France?",
        "plan": None,
        "selected_agent": "browser",
        "logs": [],
        "result": None,
    }
    res_read = browser_node(state_read)
    assert res_read["approval_required"] is False
    assert "paris" in res_read["result"].lower() or "browser" in res_read["result"].lower() or "untrusted" in res_read["result"].lower()


def test_file_agent_parsing(mock_env):
    """Tests File Agent structured document parsing capabilities."""
    state_pdf: AgentState = {
        "user_input": "Analyze doc.pdf",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    res_pdf = file_node(state_pdf)
    assert "PDF PARSED" in res_pdf["result"]
    assert "Pages: 12" in res_pdf["result"]

    state_xlsx: AgentState = {
        "user_input": "Extract data from sheet.xlsx",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    res_xlsx = file_node(state_xlsx)
    assert "XLSX PARSED" in res_xlsx["result"]
    assert "Summary" in res_xlsx["result"]


def test_voice_agent_modes(mock_env):
    """Tests Voice Agent mode routing and pipeline feedback."""
    state: AgentState = {
        "user_input": "Synthesize using engineering voice parameters",
        "plan": None,
        "selected_agent": "voice",
        "logs": [],
        "result": None,
    }
    res = voice_node(state)
    assert "ENGINEERING mode" in res["result"]
    assert any("engineering mode" in log for log in res["logs"])


def test_monitoring_agent_and_freeze(mock_env):
    """Tests Monitoring Agent statistics tracking, report aggregation, and freeze triggers."""
    # Write mock data with high failures to trigger freeze recommendation
    stats = MonitoringAgent.load_stats()
    stats["total_steps"] = 100
    stats["failures"] = 12  # 12% failure rate (> 5%)
    MonitoringAgent.save_stats(stats)

    state: AgentState = {
        "user_input": "Check ecosystem health",
        "plan": None,
        "selected_agent": "monitoring",
        "logs": [],
        "result": None,
    }
    res = monitoring_node(state)
    assert "FREEZE RECOMMENDED" in res["result"]
    assert "High failure rate" in res["result"]
    assert any("monitoring" in log for log in res["logs"])


def test_research_agent_consensus_and_proposals(mock_env, monkeypatch):
    """Tests Research Agent integration with Trust Engine and Proposal creation."""
    # Mock ask_model to return valid proposal details
    mock_json = {
        "title": "Vectored cache layout",
        "problem": "High memory consumption",
        "evidence": "Gains from academic consensus",
        "proposal": "Implement page caches",
        "expected_gain": 2.1,
        "complexity": 2,
        "confidence": 8,
        "affected_modules": ["backend/core/graph.py"]
    }
    monkeypatch.setattr(
        "backend.agents.researcher.ask_model",
        lambda prompt, role, system=None: json.dumps(mock_json)
    )

    state: AgentState = {
        "user_input": "Propose an improvement from peer-reviewed paper Optimizing Caches",
        "plan": None,
        "selected_agent": "researcher",
        "logs": [],
        "result": None,
    }
    
    # Pre-configure reputation to trigger high consensus
    from backend.core.source_trust_engine import SourceTrustEngine
    SourceTrustEngine.get_source_reputation("Google Search Snippet Summary", "verified")
    
    res = researcher_node(state)
    assert "Generated Proposal" in res["result"]
    assert any("registered proposal" in log for log in res["logs"])
