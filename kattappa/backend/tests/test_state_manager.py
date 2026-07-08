"""Tests for Phase K11.5: Cognitive State Manager."""
from __future__ import annotations

import pytest
from backend.core.state_manager import CognitiveStateManager, CognitiveState
from backend.core.attention import Attention
from backend.core.blackboard import BLACKBOARD


@pytest.fixture(autouse=True)
def clean_state():
    CognitiveStateManager.reset()
    BLACKBOARD.clear()
    yield
    CognitiveStateManager.reset()
    BLACKBOARD.clear()


def test_get_set_state():
    # Initial state should be IDLE
    assert CognitiveStateManager.get_state() == CognitiveState.IDLE

    # Set to FOCUSED
    CognitiveStateManager.set_state(CognitiveState.FOCUSED)
    assert CognitiveStateManager.get_state() == CognitiveState.FOCUSED

    # Verify blackboard publication
    history = BLACKBOARD.get_history(topic="state_change")
    assert len(history) == 1
    assert history[0].payload["current_state"] == "FOCUSED"


def test_dynamic_attention_weights():
    CognitiveStateManager.set_state(CognitiveState.EXPLORING)
    weights = CognitiveStateManager.get_attention_weights()
    assert weights["novelty"] == 0.50
    assert weights["importance"] == 0.10

    CognitiveStateManager.set_state(CognitiveState.EMERGENCY)
    weights = CognitiveStateManager.get_attention_weights()
    assert weights["novelty"] == 0.00
    assert weights["urgency"] == 0.40


def test_dynamic_memory_thresholds():
    # Base IDLE thresholds
    CognitiveStateManager.set_state(CognitiveState.IDLE)
    idle_th = CognitiveStateManager.get_memory_thresholds()
    assert idle_th["semantic"] == 0.75

    # Relaxed in EXPLORING state
    CognitiveStateManager.set_state(CognitiveState.EXPLORING)
    exploring_th = CognitiveStateManager.get_memory_thresholds()
    assert exploring_th["semantic"] == 0.60

    # Tightened in EMERGENCY state
    CognitiveStateManager.set_state(CognitiveState.EMERGENCY)
    emergency_th = CognitiveStateManager.get_memory_thresholds()
    assert emergency_th["semantic"] == 0.85


def test_state_manager_modifies_attention_composite_score():
    """Verify that changing system state changes computed attention composite priority."""
    # Input has high novelty ("radar quantum teleportation")
    obs = {
        "raw_message": "Explain radar quantum teleportation algorithms.",
        "session_id": "test-session",
    }

    # 1. State: EMERGENCY (weights urgency/risk/importance, novelty=0.0)
    CognitiveStateManager.set_state(CognitiveState.EMERGENCY)
    res_emergency = Attention.process(obs)
    score_emergency = res_emergency["attention_score"]

    # 2. State: EXPLORING (weights novelty=0.50)
    CognitiveStateManager.set_state(CognitiveState.EXPLORING)
    res_exploring = Attention.process(obs)
    score_exploring = res_exploring["attention_score"]

    # Since the input is highly novel and state change shifts weight, composite should differ
    assert score_exploring["composite"] != score_emergency["composite"]
    assert score_exploring["novelty"] > 0.6  # High novelty for unknown term
