from __future__ import annotations

import pytest
from backend.core.memory import get_git_status, build_memory_context
from backend.agents.planner import parse_reasoning_plan
from backend.agents.evaluator import detect_placeholders


def test_get_git_status():
    status = get_git_status()
    assert isinstance(status, str)
    assert len(status) > 0


def test_build_memory_context():
    context = build_memory_context("test prompt")
    assert isinstance(context, str)
    assert "Local Workspace Status" in context


def test_parse_reasoning_plan():
    sample_text = (
        "[Reasoning] We need to write a script to patch our codebase.\n"
        "[Routing] coder\n"
        "[Checklist]\n"
        "- Step 1: Create a test file\n"
        "- Step 2: Write patch code\n"
    )
    parsed = parse_reasoning_plan(sample_text)
    assert parsed["agent"] == "coder"
    assert "patch our codebase" in parsed["reasoning"]
    assert len(parsed["checklist"]) == 2
    assert parsed["checklist"][0] == "Step 1: Create a test file"
    assert parsed["checklist"][1] == "Step 2: Write patch code"


def test_parse_reasoning_plan_fallback():
    sample_text = "Some random text response that does not follow the format"
    parsed = parse_reasoning_plan(sample_text)
    assert parsed["agent"] == "evaluator"
    assert parsed["checklist"] == []


def test_detect_placeholders():
    assert detect_placeholders("def foo():\n    # TODO: implement this\n    pass") is True
    assert detect_placeholders("def foo():\n    // TODO implement\n    return") is True
    assert detect_placeholders("def foo():\n    # ... write logic here\n    pass") is True
    assert detect_placeholders("def foo():\n    pass # placeholder\n") is True
    assert detect_placeholders("def foo():\n    # your code here\n") is True
    
    # Negative cases
    assert detect_placeholders("def foo():\n    print('Hello World')\n    return 42") is False
    assert detect_placeholders("This is a normal paragraph discussing programming tasks.") is False


def test_trigger_voice_response(monkeypatch):
    import os
    import time
    from backend import main as backend_main

    spoken_text = []

    def mock_speak(text, purpose="assistant_response"):
        spoken_text.append(text)
        return "spoken"

    monkeypatch.setattr(backend_main, "speak", mock_speak)
    monkeypatch.setenv("FORCE_TEST_SPEECH", "1")

    # Non-ephemeral should speak
    backend_main._trigger_voice_response({"result": "Speak this response", "ephemeral_worker": False})
    # Ephemeral should not speak
    backend_main._trigger_voice_response({"result": "Do not speak this", "ephemeral_worker": True})

    # Since it runs in a background thread, wait a brief moment for execution
    time.sleep(0.1)

    assert "Speak this response" in spoken_text
    assert "Do not speak this" not in spoken_text


def test_get_jarvis_diagnostics():
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    response = client.get("/settings/jarvis/diagnostics")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "telemetry" in data
    assert "stats" in data
    assert "neuroseed_brain_sync" in data["telemetry"]
    assert "cyber_shield_deflectors" in data["telemetry"]
    assert "universal_translation" in data["telemetry"]
    assert "stats" in data
    assert "cpu" in data["stats"]
    assert "memory" in data["stats"]
