"""Tests for Phase K16: Predictive Cognition Layer (PredictiveEngine)."""
from __future__ import annotations

import os
import pytest
from backend.core.predictive_engine import PredictiveEngine


@pytest.fixture
def temp_db_path(tmp_path):
    return str(tmp_path / "test_predictive.db")


@pytest.fixture(autouse=True)
def clean_engine(temp_db_path):
    PredictiveEngine.reset(db_path=temp_db_path)
    yield


def test_add_and_retrieve_belief(temp_db_path):
    bid = PredictiveEngine.add_belief(
        concept="user_preference",
        statement="User prefers Linux shell",
        confidence=0.85,
        source="user_interface",
        db_path=temp_db_path
    )
    assert bid is not None
    
    b = PredictiveEngine.get_belief(bid, db_path=temp_db_path)
    assert b is not None
    assert b.concept == "user_preference"
    assert b.statement == "User prefers Linux shell"
    assert b.confidence == 0.85
    assert b.source == "user_interface"
    assert b.last_verified > 0


def test_belief_contradiction_detection(temp_db_path):
    # Add first belief
    bid1 = PredictiveEngine.add_belief(
        concept="radar_status",
        statement="Radar is operational",
        confidence=0.9,
        source="sensor",
        db_path=temp_db_path
    )
    
    # Add contradictory belief
    bid2 = PredictiveEngine.add_belief(
        concept="radar_status",
        statement="Radar is not operational",
        confidence=0.95,
        source="diagnostic",
        db_path=temp_db_path
    )
    
    b1 = PredictiveEngine.get_belief(bid1, db_path=temp_db_path)
    b2 = PredictiveEngine.get_belief(bid2, db_path=temp_db_path)
    
    assert bid2 in b1.contradictions
    assert bid1 in b2.contradictions


def test_forward_simulation_uncertainty():
    world = {"file_state": "none", "db_connected": True}
    action_write = {"action": "write_file", "params": {"path": "/tmp/a"}}
    
    # Simulating 1 step
    res1 = PredictiveEngine.simulate_action(world, action_write, steps_count=1)
    assert res1.predicted_state["file_state"] == "created"
    
    # Simulating 10 steps -> uncertainty must grow
    res10 = PredictiveEngine.simulate_action(world, action_write, steps_count=10)
    assert res10.uncertainty > res1.uncertainty
    assert res10.confidence < res1.confidence
    assert len(res10.assumptions) > 0


def test_counterfactual_engine_isolation(temp_db_path):
    # Setup master belief
    PredictiveEngine.add_belief(
        concept="auth_token",
        statement="Auth token is valid",
        confidence=0.9,
        source="system",
        db_path=temp_db_path
    )

    def sim_check_auth(context):
        # Retrieve all beliefs from the isolated temp db
        isolated_db = context["db_path"]
        beliefs = PredictiveEngine.get_all_beliefs(isolated_db)
        # Should have the master belief + the counterfactual modification
        has_hypothetical = any(b.concept == "auth_token" and "revoked" in b.statement for b in beliefs)
        return has_hypothetical

    # Run counterfactual with modification
    mods = {
        "auth_token": {"statement": "Auth token is revoked", "confidence": 1.0}
    }
    
    triggered = PredictiveEngine.simulate_counterfactual(mods, sim_check_auth, db_path=temp_db_path)
    assert triggered is True
    
    # Verify master DB was NOT polluted
    master_beliefs = PredictiveEngine.get_all_beliefs(temp_db_path)
    assert len(master_beliefs) == 1
    assert "revoked" not in master_beliefs[0].statement


def test_prediction_error_decay(temp_db_path):
    bid = PredictiveEngine.add_belief(
        concept="radar_range",
        statement="Radar range is 50km",
        confidence=0.9,
        source="sensor",
        db_path=temp_db_path
    )
    
    # Prediction matches outcome
    pred = {"range": "50km"}
    reality = {"range": "50km"}
    err = PredictiveEngine.track_prediction_error(bid, pred, reality, db_path=temp_db_path)
    assert err == 0.0
    
    # Retrieve and verify confidence remains 0.9
    b = PredictiveEngine.get_belief(bid, db_path=temp_db_path)
    assert b.confidence == 0.9

    # Prediction fails to match outcome
    reality_failed = {"range": "10km"}
    err_failed = PredictiveEngine.track_prediction_error(bid, pred, reality_failed, db_path=temp_db_path)
    assert err_failed > 0.0
    
    # Retrieve and verify confidence degraded
    b_degraded = PredictiveEngine.get_belief(bid, db_path=temp_db_path)
    assert b_degraded.confidence < 0.9
