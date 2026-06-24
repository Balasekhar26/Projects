"""Comprehensive validation suite for Step 19.5 Agent Runtime Validation."""

from __future__ import annotations

import json
import time
import datetime
import pytest
from unittest.mock import patch, MagicMock

from backend.core.rbil import RBIL, IntentClassifier
from backend.agents.planner import planner_node
from backend.agents.coder import coder_node
from backend.core.action_broker import ActionBroker
from backend.main import handle_fast_path, _build_direct_model_prompt
import backend.agents.browser
import backend.agents.desktop


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.memory as mem_module
    monkeypatch.setenv("KATTAPPA_DATA_DIR", str(tmp_path))
    # Clear memory schema cache if any
    mem_module._schema_ensured = False
    yield


# ── Context Tests & Session Memory ───────────────────────────────────────────

def test_build_direct_model_prompt_injects_history_and_date(isolated_db):
    """Verify that _build_direct_model_prompt loads chat history and injects date/time."""
    from backend.core.memory import memory
    session = memory.get_or_create_primary_chat_session()
    
    # Add older chat history
    msg1 = memory.add_chat_message(session["id"], "user", "My name is Bala")
    msg2 = memory.add_chat_message(session["id"], "assistant", "Hello Bala!")
    
    current_msg = memory.add_chat_message(session["id"], "user", "What's my name?")
    
    prompt = _build_direct_model_prompt("What's my name?", session["id"], current_msg["id"])
    
    assert "System Context:" in prompt
    assert "Current Date:" in prompt
    assert "Current Local Time:" in prompt
    assert "Recent conversation history:" in prompt
    assert "user: My name is Bala" in prompt
    assert "assistant: Hello Bala!" in prompt
    assert "User: What's my name?" in prompt


# ── Tool Tests ────────────────────────────────────────────────────────────────

def test_intent_classifier_matches_various_date_formats():
    """Verify IntentClassifier matches both today's date and today date."""
    res1 = IntentClassifier.evaluate("what is today's date")
    assert res1 is not None
    assert res1["agent"] == "rbil_date"
    
    res2 = IntentClassifier.evaluate("what is today date")
    assert res2 is not None
    assert res2["agent"] == "rbil_date"
    
    res3 = IntentClassifier.evaluate("current date")
    assert res3 is not None
    assert res3["agent"] == "rbil_date"


def test_handle_fast_path_bypasses_multi_step():
    """Verify that handle_fast_path returns None if 'then' or 'and' is present."""
    assert handle_fast_path("open chrome then test speed") is None
    assert handle_fast_path("open chrome and check speed") is None


def test_handle_fast_path_mac_chrome_launch():
    """Verify handle_fast_path chrome launch runs open command on mac."""
    with patch("platform.system", return_value="Darwin"), \
         patch("subprocess.Popen") as mock_popen:
        res = handle_fast_path("open chrome")
        assert res is not None
        mock_popen.assert_called_once_with(["open", "-a", "Google Chrome"])


# ── Coding Tests ──────────────────────────────────────────────────────────────

def test_coder_fallback_generates_markdown_code_block():
    """Verify coder fallback for 'hello world' returns formatted code block."""
    state = {
        "user_input": "Write python hello world",
        "plan": "Generate hello world code",
        "logs": []
    }
    
    # Mock ask_model to return code block
    mock_code = '```python\nprint("Hello World")\n```'
    with patch("backend.agents.coder.ask_model", return_value=mock_code) as mock_ask:
        res_state = coder_node(state)
        assert "print(\"Hello World\")" in res_state["result"]
        assert "```python" in res_state["result"]


# ── Multi-Step Planner Tests ──────────────────────────────────────────────────

def test_planner_routes_multi_step_chrome_speedtest():
    """Verify planner splits 'open chrome then test speed' into desktop & browser steps."""
    state = {
        "user_input": "open chrome then test speed",
        "logs": [],
        "memory_context": "test workspace"
    }
    
    res_state = planner_node(state)
    assert "execution_steps" in res_state
    # desktop opens Chrome, browser runs speed test
    assert "desktop" in res_state["execution_steps"] or res_state["selected_agent"] == "desktop"
    assert "browser" in res_state["execution_steps"] or res_state["selected_agent"] == "browser"


def test_action_broker_executes_browser_speedtest():
    """Verify ActionBroker successfully executes BROWSER_SPEEDTEST."""
    params = {}
    mock_speed_res = "Internet Speed Test Results: 45 Mbps."
    
    with patch("backend.core.macros.browser_macros.execute_speedtest", return_value=mock_speed_res) as mock_macro:
        broker_res = ActionBroker.intake_request("browser", "BROWSER_SPEEDTEST", params, {})
        assert broker_res["success"] is True
        assert broker_res["result"]["content"] == mock_speed_res
        mock_macro.assert_called_once()
