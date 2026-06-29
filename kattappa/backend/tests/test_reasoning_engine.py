from __future__ import annotations

import pytest
from backend.core.reasoning_engine import ReasoningEngine


def test_reasoning_engine_ready_to_plan():
    res = ReasoningEngine.analyze(
        goal_title="Compile Python script",
        goal_description="Create a compiler task for test_script.py and run local checks."
    )
    assert res["status"] == "READY_TO_PLAN"
    assert res["domain"] == "Software Development"
    assert len(res["assumptions"]) > 0
    assert not res["missing_information"]
    assert not res["clarification_questions"]


def test_reasoning_engine_requires_clarification():
    res = ReasoningEngine.analyze(
        goal_title="Compile codebase",
        goal_description="Compile all build items in the source folder without specifying language or location."
    )
    assert res["status"] == "REQUIRES_CLARIFICATION"
    assert "Programming language choice is unspecified." in res["missing_information"]
    assert len(res["clarification_questions"]) >= 2


def test_reasoning_engine_risks_detected():
    res = ReasoningEngine.analyze(
        goal_title="Delete database logs as root admin",
        goal_description="Clean target configuration files using sudo rm -rf commands."
    )
    assert len(res["risks"]) >= 2
    categories = {r["category"] for r in res["risks"]}
    assert "REVERSIBILITY_RISK" in categories
    assert "PRIVILEGE_RISK" in categories
