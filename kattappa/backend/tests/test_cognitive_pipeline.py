"""Comprehensive verification tests for Steps 20 & 25 Cognitive Thinking Pipeline."""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from backend.core.observer import Observer
from backend.core.attention import Attention
from backend.core.memory_recall import MemoryRecall
from backend.core.council_debate import CouncilDebate
from backend.core.safety_review import SafetyReview
from backend.core.graph import run_graph


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.memory as mem_module
    monkeypatch.setenv("KATTAPPA_DATA_DIR", str(tmp_path))
    mem_module._schema_ensured = False
    yield


# ── Observation Layer Tests ──────────────────────────────────────────────────

def test_observer_gathers_full_context(isolated_db):
    """Verify that Observer extracts platform, time, date, and workspace status."""
    frame = Observer.observe(
        raw_message="Hello Kattappa",
        session_id="test-session",
        active_document={
            "filepath": "/path/to/test.py",
            "cursor_line": 15,
            "language": "python"
        }
    )

    assert frame["raw_message"] == "Hello Kattappa"
    assert frame["session_id"] == "test-session"
    assert "system_time" in frame
    assert "system_date" in frame
    assert "os_platform" in frame
    assert frame["active_document"]["filepath"] == "/path/to/test.py"
    assert frame["active_document"]["cursor_line"] == 15
    assert frame["active_document"]["language"] == "python"
    assert "workspace_metadata" in frame
    assert "git_status" in frame["workspace_metadata"]


# ── Attention Layer Tests ─────────────────────────────────────────────────────

def test_attention_early_exits(isolated_db):
    """Verify early exit triggers for Fast Path, RBIL, and Response Cache."""
    # Mock Observer Frame
    obs_frame = {
        "raw_message": "what is today's date",
        "session_id": "test-session",
        "active_document": None
    }

    # 1. RBIL exit check
    attn_res = Attention.process(obs_frame)
    assert attn_res["early_exit"] is not None
    assert attn_res["early_exit"]["type"] == "rbil"
    payload = attn_res["early_exit"]["payload"]
    assert "response" in payload or "result" in payload

    # 2. Regular query complexity and requires_tools evaluation
    obs_frame_2 = {
        "raw_message": "Open chrome and run a speed test then convert code",
        "session_id": "test-session",
        "active_document": None
    }
    attn_res_2 = Attention.process(obs_frame_2)
    assert attn_res_2["early_exit"] is None
    assert attn_res_2["complexity_level"] == 2
    assert attn_res_2["requires_tools"] is True
    assert "chrome" in attn_res_2["focus_keywords"]


# ── Memory Recall Layer Tests ─────────────────────────────────────────────────

def test_memory_recall_merges_sources(isolated_db):
    """Verify parallel fetch matches from SQLite episodic memory and relationship notes."""
    attention_frame = {
        "clean_message": "My name is Bala",
        "focus_keywords": ["bala"]
    }

    payload = MemoryRecall.recall(attention_frame, "test-session")
    assert "episodic_history" in payload
    assert "semantic_context" in payload
    assert "cognitive_episodes" in payload
    assert "relationship_notes" in payload


# ── Safety Review Layer Tests ─────────────────────────────────────────────────

def test_safety_review_blocks_risk_5(isolated_db):
    """Verify that SafetyReview blocks risk level 5 or destructive command actions."""
    # 1. Prohibited Action Plan
    bad_plan = {
        "steps": [
            {
                "tool": "FORMAT_DRIVE",
                "action": "execute",
                "args": {"target": "C:"}
            }
        ]
    }
    review_res = SafetyReview.review(bad_plan, "test-session")
    assert review_res["is_safe"] is False
    assert "FORMAT_DRIVE" in review_res["rejection_reason"]
    assert review_res["risk_level"] == 5

    # 2. Safe Action Plan
    safe_plan = {
        "steps": [
            {
                "tool": "READ_FILE",
                "action": "execute",
                "args": {"path": "main.py"}
            }
        ]
    }
    review_res_2 = SafetyReview.review(safe_plan, "test-session")
    assert review_res_2["is_safe"] is True
    assert review_res_2["risk_level"] == 0
