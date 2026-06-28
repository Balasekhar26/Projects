"""Tests for Phase K10: Executive Attention 2.0."""
from __future__ import annotations

import pytest
from backend.core.attention import Attention, AttentionScore


def test_attention_score_dataclass():
    score = AttentionScore(
        importance=0.8,
        urgency=0.6,
        novelty=0.4,
        risk=0.2,
        opportunity=0.5,
        composite=0.51,
    )
    assert score.importance == 0.8
    assert score.urgency == 0.6
    assert score.novelty == 0.4
    assert score.risk == 0.2
    assert score.opportunity == 0.5
    assert score.composite == 0.51

    d = score.to_dict()
    assert d["importance"] == 0.8
    assert d["composite"] == 0.51


def test_attention_process_returns_score_dict():
    obs = {
        "raw_message": "Hello, let's chat about nothing special.",
        "session_id": "test-session",
    }
    res = Attention.process(obs)
    assert "attention_score" in res
    score = res["attention_score"]
    assert "importance" in score
    assert "urgency" in score
    assert "novelty" in score
    assert "risk" in score
    assert "opportunity" in score
    assert "composite" in score


def test_urgency_detection():
    obs_normal = {
        "raw_message": "Can you check the current status?",
        "session_id": "test-session",
    }
    obs_urgent = {
        "raw_message": "ASAP! There is a critical deadline due in 5 minutes!",
        "session_id": "test-session",
    }

    res_normal = Attention.process(obs_normal)
    res_urgent = Attention.process(obs_urgent)

    score_normal = res_normal["attention_score"]
    score_urgent = res_urgent["attention_score"]

    # Urgency and Importance should both be boosted
    assert score_urgent["urgency"] > score_normal["urgency"]
    assert score_urgent["importance"] > score_normal["importance"]


def test_opportunity_detection():
    obs_normal = {
        "raw_message": "Write a script to print hello.",
        "session_id": "test-session",
    }
    obs_opp = {
        "raw_message": "Let's study mathematics and refactor the core algorithms for long-term growth.",
        "session_id": "test-session",
    }

    res_normal = Attention.process(obs_normal)
    res_opp = Attention.process(obs_opp)

    score_normal = res_normal["attention_score"]
    score_opp = res_opp["attention_score"]

    assert score_opp["opportunity"] > score_normal["opportunity"]


def test_risk_detection():
    obs_normal = {
        "raw_message": "Create a file named test.py",
        "session_id": "test-session",
    }
    obs_risky = {
        "raw_message": "rm -rf / && delete all database records immediately",
        "session_id": "test-session",
    }

    res_normal = Attention.process(obs_normal)
    res_risky = Attention.process(obs_risky)

    score_normal = res_normal["attention_score"]
    score_risky = res_risky["attention_score"]

    assert score_risky["risk"] > score_normal["risk"]
    assert res_risky["stakes_level"] == "high"
    assert res_risky["reversibility"] == "irreversible"


def test_path_selection():
    # Risky + urgent should be COUNCIL or DEEP
    obs_critical = {
        "raw_message": "Wipe the production database immediately! Critical deadline!",
        "session_id": "test-session",
    }
    res_critical = Attention.process(obs_critical)
    assert res_critical["path_selected"] in ("DEEP", "COUNCIL")

    # Simple chat should be FAST
    obs_simple = {
        "raw_message": "Hello there",
        "session_id": "test-session",
    }
    res_simple = Attention.process(obs_simple)
    # Simple hello is early exited by RBIL, so let's check its path selected
    assert res_simple["path_selected"] == "FAST"
