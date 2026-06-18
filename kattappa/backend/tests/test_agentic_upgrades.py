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
