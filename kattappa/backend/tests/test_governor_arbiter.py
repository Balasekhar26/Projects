import pytest
from backend.core.governor import (
    DecisionArbiter,
    RuntimeScheduler,
    GovernorAction,
    SystemPolicyMode,
    BaseGovernor
)
from backend.core.governor.event_bus import EventBus

class MockGovernor(BaseGovernor):
    def __init__(self, capacity: float, risk: float, priority: int, confidence: float, action: GovernorAction, reason: str):
        super().__init__(priority=priority)
        self.capacity = capacity
        self.risk = risk
        self.confidence = confidence
        self.action = action
        self.reason = reason

    def get_metrics(self) -> dict:
        return {}

    def assess(self) -> dict:
        return {
            "available_capacity": self.capacity,
            "risk_score": self.risk,
            "priority": self.priority,
            "confidence": self.confidence,
            "recommended_action": self.action,
            "reason": self.reason,
            "metrics": {}
        }

def test_arbiter_safety_override():
    """Verifies that a high priority safety governor overrides weighted votes."""
    arbiter = DecisionArbiter()
    
    # Set all governors to NOMINAL
    for name in arbiter.governors:
        arbiter.governors[name] = MockGovernor(
            capacity=90.0, risk=0.1, priority=arbiter.governors[name].priority,
            confidence=1.0, action=GovernorAction.NONE, reason="Nominal"
        )
        
    # Inject thermal override (Priority 100, Action PAUSE)
    arbiter.governors["thermal"] = MockGovernor(
        capacity=10.0, risk=0.9, priority=100, confidence=1.0, action=GovernorAction.PAUSE,
        reason="Imminent thermal throttle"
    )
    
    # Inject CPU ECO recommendation (Priority 60)
    arbiter.governors["cpu"] = MockGovernor(
        capacity=40.0, risk=0.5, priority=60, confidence=1.0, action=GovernorAction.ECO,
        reason="CPU elevated"
    )
    
    result = arbiter.assess_system()
    
    # Thermal PAUSE override should win immediately
    assert result["recommended_action"] == GovernorAction.PAUSE
    assert result["safety_override_triggered"] is True
    assert result["worst_governor"] == "thermal"
    assert result["active_policy"] == SystemPolicyMode.ECO

def test_arbiter_low_confidence_sensor_ignored():
    """Verifies that safety overrides are bypassed if sensor confidence is degraded (< 0.3)."""
    arbiter = DecisionArbiter()
    
    for name in arbiter.governors:
        arbiter.governors[name] = MockGovernor(
            capacity=95.0, risk=0.05, priority=arbiter.governors[name].priority,
            confidence=1.0, action=GovernorAction.NONE, reason="Nominal"
        )
        
    # Inject Battery critical override but with degraded confidence (0.2)
    arbiter.governors["battery"] = MockGovernor(
        capacity=5.0, risk=0.95, priority=90, confidence=0.2, action=GovernorAction.PAUSE,
        reason="Battery reports critical"
    )
    
    # Inject CPU ECO recommendation (Priority 60, confidence 1.0)
    arbiter.governors["cpu"] = MockGovernor(
        capacity=45.0, risk=0.5, priority=60, confidence=1.0, action=GovernorAction.ECO,
        reason="CPU ECO"
    )
    
    result = arbiter.assess_system()
    
    # Battery override should be ignored. CPU weighted vote ECO should win.
    assert result["recommended_action"] == GovernorAction.ECO
    assert result["safety_override_triggered"] is False
    assert result["worst_governor"] == "cpu"

def test_event_bus_publishing():
    """Verifies that the arbiter publishes decisions to the Event Bus."""
    arbiter = DecisionArbiter()
    
    received_data = {}
    def on_decision(topic, data):
        received_data.update(data)
        
    # Subscribe to event bus
    EventBus().subscribe("governor/decision", on_decision)
    
    # Run assess
    arbiter.assess_system()
    
    # Verify publication
    assert "recommended_action" in received_data
    assert "active_policy" in received_data
    assert "worst_governor" in received_data
    
    # Unsubscribe
    EventBus().unsubscribe("governor/decision", on_decision)
