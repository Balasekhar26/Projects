from __future__ import annotations

import pytest
import datetime
import os
import pathlib
import json

from backend.core.rbil import RBIL, IntentClassifier, ArchetypeEngine, MetricsTracker, METRICS_PATH


def test_intent_greeting_and_farewell():
    # Greetings
    res = IntentClassifier.evaluate("Hi there!")
    assert res is not None
    assert "ready" in res["result"].lower()
    assert res["agent"] == "rbil_greeting"

    # Farewell
    res = IntentClassifier.evaluate("Goodbye, see ya!")
    assert res is not None
    assert "goodbye" in res["result"].lower()
    assert res["agent"] == "rbil_farewell"


def test_intent_time_and_date():
    # Time
    res = IntentClassifier.evaluate("What time is it right now?")
    assert res is not None
    assert res["agent"] == "rbil_time"
    assert ":" in res["result"]

    # Date
    res = IntentClassifier.evaluate("Tell me today's date")
    assert res is not None
    assert res["agent"] == "rbil_date"
    # Should contain the current year (2026)
    assert "2026" in res["result"]


def test_intent_calculator():
    res = IntentClassifier.evaluate("calculate (20 * 5) - 30")
    assert res is not None
    assert "70" in res["result"]
    assert res["agent"] == "rbil_calculator"

    # Invalid math should be ignored (None)
    assert IntentClassifier.evaluate("calculate 2 + abc") is None


def test_intent_unit_conversion():
    # kg to lbs
    res = IntentClassifier.evaluate("convert 10 kg to lbs")
    assert res is not None
    assert "22.04" in res["result"]
    assert res["agent"] == "rbil_converter"

    # C to F
    res = IntentClassifier.evaluate("100 C to F")
    assert res is not None
    assert "212" in res["result"]

    # miles to km
    res = IntentClassifier.evaluate("10 miles to km")
    assert res is not None
    assert "16.09" in res["result"]


def test_intent_faqs_and_projects():
    # FAQ
    res = IntentClassifier.evaluate("Who are you")
    assert res is not None
    assert "kattappa" in res["result"].lower()
    assert res["agent"] == "rbil_faq"

    # Projects list
    res = IntentClassifier.evaluate("show all projects")
    assert res is not None
    assert "voltis" in res["result"].lower()
    assert "universal-translator" in res["result"].lower()
    assert res["agent"] == "rbil_projects"


def test_archetype_engine_general():
    # General query
    res = ArchetypeEngine.parse_and_interpret("Explain the archetypes")
    assert res is not None
    assert "Rama" in res
    assert "Krishna" in res
    assert "Brahma" in res


def test_archetype_engine_profile():
    # Parsing custom values
    query = "Value Archetypes Rama 30% Krishna 5% Brahma 30% Shiva 5% Kattappa 30% what is the meaning of the readings in you"
    res = ArchetypeEngine.parse_and_interpret(query)
    assert res is not None
    assert "Rama**: 30%" in res
    assert "Brahma**: 30%" in res
    assert "Kattappa**: 30%" in res
    assert "disciplined, execution-oriented builder" in res


def test_escalation_classification():
    # Level 1/2 simple questions
    assert RBIL.classify_escalation_level("what is the capital of Japan?") == 1
    assert RBIL.classify_escalation_level("explain how a car engine works in detail") == 2

    # Level 4 complex questions
    assert RBIL.classify_escalation_level("create a python script to parse logs and save it to file.py") == 4
    assert RBIL.classify_escalation_level("run setup.bat in terminal") == 4
    assert RBIL.classify_escalation_level("/terminal git status") == 4
    assert RBIL.classify_escalation_level("what is the financial forecast for AAPL?") == 4


def test_metrics_tracker(tmp_path):
    # Mock file path for testing
    orig_path = METRICS_PATH
    test_metrics_file = tmp_path / "test_metrics.json"
    
    import backend.core.rbil as rbil_mod
    rbil_mod.METRICS_PATH = test_metrics_file

    try:
        # Load initially
        m = MetricsTracker.load()
        assert m["llm_calls_avoided"] == 0

        # Record hit
        MetricsTracker.record_hit("rule")
        m2 = MetricsTracker.load()
        assert m2["llm_calls_avoided"] == 1
        assert m2["rule_hits"] == 1

        # Record cache hit
        MetricsTracker.record_hit("cache")
        m3 = MetricsTracker.load()
        assert m3["llm_calls_avoided"] == 2
        assert m3["cache_hits"] == 1

        # Record timeout prevented
        MetricsTracker.record_timeout_prevented()
        m4 = MetricsTracker.load()
        assert m4["timeouts_prevented"] == 1

    finally:
        # Restore path
        rbil_mod.METRICS_PATH = orig_path
        if test_metrics_file.exists():
            test_metrics_file.unlink()
