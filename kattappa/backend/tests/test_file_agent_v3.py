import json
import os
import pytest
from pathlib import Path

from backend.agents.file_agent import file_node, is_safe_file_path
from backend.core.config import runtime_data_root
from backend.core.state import AgentState


def test_classify_browser_action():
    # We will test classifying actions via file_node classification logic
    state: AgentState = {
        "user_input": "Delete dataset.csv",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    res = file_node(state)
    assert "strictly prohibited" in res["result"].lower() or "approval needed" in res["result"].lower()


def test_file_agent_provenance_tagging():
    # Test CSV parsing with provenance tag checks
    test_file = runtime_data_root() / "dataset.csv"
    test_file.write_text("id,name,value\n1,Bala,100\n2,Shekhar,200", encoding="utf-8")
    
    state: AgentState = {
        "user_input": f"Parse the table {test_file}",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    
    res = file_node(state)
    assert res["result"] is not None
    
    # Verify result is structured JSON and contains the correct fields
    data = json.loads(res["result"])
    assert data["source_file"] == str(test_file)
    assert "CSV PARSED" in data["content"]
    assert "Columns: ['id', 'name', 'value']" in data["content"]
    assert data["trust_score"] == 85
    assert data["provenance"] == "UNTRUSTED_DATA"
    assert "timestamp" in data


def test_file_agent_safe_reads():
    # Test simple text parsing
    test_file = runtime_data_root() / "readme.txt"
    test_file.write_text("Kattappa V3 safe read content.", encoding="utf-8")
    
    state: AgentState = {
        "user_input": f"Read plain text from {test_file}",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    res = file_node(state)
    data = json.loads(res["result"])
    assert "TEXT PARSED" in data["content"]
    assert "Kattappa V3 safe read content" in data["content"]
    assert data["provenance"] == "UNTRUSTED_DATA"


def test_file_agent_boundary_checks():
    # 1. Accessing file outside workspace root
    bad_path = "/etc/passwd"
    assert is_safe_file_path(bad_path) is False
    
    state_bad: AgentState = {
        "user_input": f"Parse the document {bad_path}",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    res_bad = file_node(state_bad)
    assert "strictly prohibited" in res_bad["result"].lower()
    assert any("blocked" in log for log in res_bad["logs"])

    # 2. Accessing protected core files inside workspace
    protected_file = "backend/core/safety.py"
    assert is_safe_file_path(protected_file) is False
    
    state_protected: AgentState = {
        "user_input": f"Read the code from {protected_file}",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    res_protected = file_node(state_protected)
    assert "strictly prohibited" in res_protected["result"].lower()


def test_file_agent_blocked_mutating_actions():
    # Delete original file
    state_del: AgentState = {
        "user_input": "Delete dataset.csv in workspace",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    res_del = file_node(state_del)
    assert "strictly prohibited" in res_del["result"].lower() or "approval needed" in res_del["result"].lower()

    # Modify / Edit original file
    state_mod: AgentState = {
        "user_input": "Write some text to config.txt in workspace",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    res_mod = file_node(state_mod)
    assert "strictly prohibited" in res_mod["result"].lower() or "approval needed" in res_mod["result"].lower()
