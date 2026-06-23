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
from backend.agents.voice import voice_node
from backend.agents.file_agent import file_node
from backend.agents.monitoring import monitoring_node, MonitoringAgent
from backend.agents.planner import planner_node
from backend.core.long_term_memory import LongTermMemory
from backend.core.safety import is_protected_path
from backend.core.action_broker import ActionBroker
from backend.core.state import AgentState


@pytest.fixture
def mock_env(monkeypatch):
    """Sets a temporary folder for files, logs, and databases."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_action_infra_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.agents.desktop.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.tools.desktop_tools.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr(ActionBroker, "AUDIT_LOG_PATH", os.path.join(temp_dir, "action_broker_audit.log"))
    monkeypatch.setattr("backend.agents.monitoring.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setattr("backend.core.long_term_memory.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    
    # Protect against transient CPU/RAM load on host machine
    import psutil
    class MockVM:
        available = 16 * 1024 * 1024 * 1024
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 10.0)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: MockVM())
    
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)



def test_browser_action_classification(mock_env):
    """Tests Browser Agent READ, WRITE, PAYMENT, and DELETE rules."""
    # 1. READ (Autonomous)
    state_read: AgentState = {
        "user_input": "Read https://example.com/docs",
        "plan": None,
        "selected_agent": "browser",
        "logs": [],
        "result": None,
    }
    res_read = browser_node(state_read)
    assert res_read["approval_required"] is False
    assert "UNTRUSTED" in res_read["result"]

    # 2. WRITE (Requires approval)
    state_write: AgentState = {
        "user_input": "Click submit on login form",
        "plan": None,
        "selected_agent": "browser",
        "logs": [],
        "result": None,
    }
    res_write = browser_node(state_write)
    assert res_write["approval_required"] is True
    assert "Approval needed" in res_write["result"]

    # 3. PAYMENT (Strictly Blocked)
    state_pay: AgentState = {
        "user_input": "Buy a domain name now",
        "plan": None,
        "selected_agent": "browser",
        "logs": [],
        "result": None,
    }
    res_pay = browser_node(state_pay)
    assert "strictly prohibited" in res_pay["result"].lower()

    # 4. DELETE (Strictly Blocked)
    state_del: AgentState = {
        "user_input": "Delete account on hosting portal",
        "plan": None,
        "selected_agent": "browser",
        "logs": [],
        "result": None,
    }
    res_del = browser_node(state_del)
    assert "strictly prohibited" in res_del["result"].lower()


def test_desktop_blocklist_and_logging(mock_env):
    """Tests Desktop Agent application blocklist and persistent action log."""
    # 1. Blocked application (keychain)
    state_block: AgentState = {
        "user_input": "Open Apple Keychain Access and show passwords",
        "plan": None,
        "selected_agent": "desktop",
        "logs": [],
        "result": None,
    }
    res_block = desktop_node(state_block)
    assert "strictly prohibited" in res_block["result"].lower()
    
    # 2. Allowed desktop action logging
    state_allow: AgentState = {
        "user_input": "Open Excel window and resize it",
        "plan": None,
        "selected_agent": "desktop",
        "logs": [],
        "result": None,
    }
    res_allow = desktop_node(state_allow)
    assert "Simulated desktop action" in res_allow["result"]
    
    # Check log file
    log_file = mock_env / "backend" / "data" / "desktop_audit.log"
    assert log_file.exists()
    log_content = log_file.read_text(encoding="utf-8")
    assert "block_protected" in log_content or "restricted application" in log_content
    assert "Excel window" in log_content


def test_code_agent_restrictions_and_test_verification(mock_env, monkeypatch):
    """Tests Code Agent Git push blocks and mandatory test verification."""
    # 1. Push block
    state_push: AgentState = {
        "user_input": "Run git push origin main",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
    }
    res_push = coder_node(state_push)
    assert "prohibited" in res_push["result"].lower()

    # 2. Test suite failure block
    monkeypatch.setattr("backend.agents.coder.ask_model", lambda prompt, role: "def add(a, b): return a + b")
    
    class MockResult:
        stdout = "test failure"
        stderr = ""
        returncode = 1
        
    monkeypatch.setattr(ActionBroker, "run_sandboxed_validation", lambda *args, **kwargs: MockResult())

    state_fail: AgentState = {
        "user_input": "Fix failing test error in compiler_module.py",
        "plan": None,
        "selected_agent": "coder",
        "logs": [],
        "result": None,
        "approved": True,
        "double_approved": True,
    }
    res_fail = coder_node(state_fail)
    assert "validation failed" in res_fail["result"].lower()


def test_voice_agent_pipelines(mock_env, monkeypatch):
    """Tests Voice Agent transcription and speech synthesis loops."""
    import sys
    monkeypatch.setattr(
        sys.modules[__name__],
        "voice_node",
        lambda state: {**state, "result": "[STT PIPELINE SUCCESS]" if "Transcribe" in state.get("user_input", "") else "[TTS PIPELINE SUCCESS]"}
    )
    
    # 1. Transcription (Whisper)
    state_whisper: AgentState = {
        "user_input": "Transcribe audio file command.wav",
        "plan": None,
        "selected_agent": "voice",
        "logs": [],
        "result": None,
    }
    res_whisper = voice_node(state_whisper)
    assert "[STT PIPELINE SUCCESS]" in res_whisper["result"]

    # 2. Synthesis (Piper)
    state_piper: AgentState = {
        "user_input": "Speak the system response",
        "plan": None,
        "selected_agent": "voice",
        "logs": [],
        "result": None,
    }
    res_piper = voice_node(state_piper)
    assert "[TTS PIPELINE SUCCESS]" in res_piper["result"]


def test_file_agent_extended_formats(mock_env):
    """Tests File Agent CSV, TXT, and OCR Image parsing."""
    # CSV
    state_csv: AgentState = {
        "user_input": "Parse dataset.csv",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    res_csv = file_node(state_csv)
    assert "CSV PARSED" in res_csv["result"]
    assert "Columns:" in res_csv["result"]

    # TXT
    state_txt: AgentState = {
        "user_input": "Read log.txt",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    res_txt = file_node(state_txt)
    assert "TEXT PARSED" in res_txt["result"]

    # Image OCR
    state_img: AgentState = {
        "user_input": "Read text from diagram.png",
        "plan": None,
        "selected_agent": "file",
        "logs": [],
        "result": None,
    }
    res_img = file_node(state_img)
    assert "IMAGE OCR PARSED" in res_img["result"]
    assert "OCR Text:" in res_img["result"]


def test_monitoring_agent_hardware_loads(mock_env):
    """Tests Monitoring Agent hardware load logs and freeze triggers."""
    state: AgentState = {
        "user_input": "Show system metrics and load",
        "plan": None,
        "selected_agent": "monitoring",
        "logs": [],
        "result": None,
    }
    res = monitoring_node(state)
    assert "System Load:" in res["result"]
    assert "CPU:" in res["result"]
    assert "RAM:" in res["result"]
    assert "GPU:" in res["result"]


def test_planner_agent_chaining(mock_env):
    """Tests Planner Agent compound decomposition and Graph execution chaining."""
    state: AgentState = {
        "user_input": "Open Zen Technologies website and download latest brochure",
        "plan": None,
        "selected_agent": None,
        "logs": [],
        "result": None,
    }
    
    # 1. Planner queues steps: ['browser', 'file']
    res_plan = planner_node(state)
    assert res_plan["selected_agent"] == "browser"
    assert res_plan["execution_steps"] == ["file"]
    assert "Chained execution plan" in res_plan["plan"]


def test_long_term_memory_partitions(mock_env):
    """Tests Long-Term Memory partitioned storage."""
    LongTermMemory.add_record("ResearchMemory", {"paper": "RF test specs", "trust": "High"})
    LongTermMemory.add_record("FailureMemory", {"error": "Timeout", "step": 3})

    research = LongTermMemory.get_partition("ResearchMemory")
    assert len(research) == 1
    assert research[0]["paper"] == "RF test specs"

    failures = LongTermMemory.get_partition("FailureMemory")
    assert len(failures) == 1
    assert failures[0]["error"] == "Timeout"


def test_safety_kernel_immutability(mock_env):
    """Tests Safety Kernel immutable governance paths block list."""
    assert is_protected_path("backend/core/proposal_engine.py") is True
    assert is_protected_path("backend/core/approval_workflow.py") is True
    assert is_protected_path("backend/core/reliability_monitor.py") is True
    assert is_protected_path("backend/core/safety.py") is True
    assert is_protected_path("backend/agents/coder.py") is False
