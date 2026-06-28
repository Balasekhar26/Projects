import pytest
from backend.core.governor import (
    DecisionArbiter,
    RuntimeScheduler,
    GovernorAction,
    SystemPolicyMode
)

def test_arbiter_nominal_real_system():
    """Verifies that the arbiter can poll real system metrics without throwing errors."""
    arbiter = DecisionArbiter()
    result = arbiter.assess_system()
    
    # Under standard test runner conditions, indicators should be nominal or warning, not crashed.
    assert "recommended_action" in result
    assert "active_policy" in result
    assert "worst_governor" in result
    assert "max_risk_score" in result
    assert "governor_details" in result
    
    # Check that details are populated for all governors
    details = result["governor_details"]
    for gov_name in ["cpu", "gpu", "memory", "thermal", "battery", "network", "disk", "latency"]:
        assert gov_name in details
        assert "available_capacity" in details[gov_name]
        assert "risk_score" in details[gov_name]
        assert "recommended_action" in details[gov_name]

def test_scheduler_limits_adaptation():
    """Verifies that the scheduler maps policies correctly to limits."""
    scheduler = RuntimeScheduler()
    limits = scheduler.get_execution_limits()
    
    # Check that limits keys exist
    assert "policy_mode" in limits
    assert "recommended_action" in limits
    assert "should_pause" in limits
    assert "max_workers" in limits
    assert "context_length_cap" in limits
    assert "microbatch_limit" in limits
    
    # Let's mock a thermal warning and see if it adaptively pauses / cuts limits
    class MockArbiter:
        def assess_system(self):
            return {
                "recommended_action": GovernorAction.PAUSE,
                "active_policy": SystemPolicyMode.ECO,
                "worst_governor": "thermal",
                "max_risk_score": 0.95,
                "priority": 8,
                "governor_details": {}
            }
            
    mock_scheduler = RuntimeScheduler(arbiter=MockArbiter())
    mock_limits = mock_scheduler.get_execution_limits()
    
    assert mock_limits["should_pause"] is True
    assert mock_limits["max_workers"] == 1
    assert mock_limits["context_length_cap"] == 256
    assert mock_limits["microbatch_limit"] == 1
    
    # Let's mock an ECO battery drop
    class MockEcoArbiter:
        def assess_system(self):
            return {
                "recommended_action": GovernorAction.ECO,
                "active_policy": SystemPolicyMode.ECO,
                "worst_governor": "battery",
                "max_risk_score": 0.65,
                "priority": 5,
                "governor_details": {}
            }
            
    mock_eco_scheduler = RuntimeScheduler(arbiter=MockEcoArbiter())
    mock_eco_limits = mock_eco_scheduler.get_execution_limits()
    
    assert mock_eco_limits["should_pause"] is False
    assert mock_eco_limits["max_workers"] == 1
    assert mock_eco_limits["context_length_cap"] == 512
    assert mock_eco_limits["microbatch_limit"] == 1
