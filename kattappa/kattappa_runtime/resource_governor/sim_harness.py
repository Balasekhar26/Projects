#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

# Add workspace to path
WORKSPACE_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from backend.core.governor import (
    DecisionArbiter,
    GovernorAction,
    SystemPolicyMode
)

class MockGovernor:
    def __init__(self, capacity: float, risk: float, priority: int, confidence: float, action: GovernorAction, reason: str, metrics: dict):
        self.capacity = capacity
        self.risk = risk
        self.priority = priority
        self.confidence = confidence
        self.action = action
        self.reason = reason
        self.metrics = metrics

    def assess(self):
        return {
            "available_capacity": self.capacity,
            "risk_score": self.risk,
            "priority": self.priority,
            "confidence": self.confidence,
            "recommended_action": self.action,
            "reason": self.reason,
            "metrics": self.metrics
        }

class TestResourceGovernorSimulation(unittest.TestCase):
    """
    RG-Sim: Simulation harness verifying the Decision Arbiter's consolidated
    actions and policy mode selections under simulated workloads and hardware stress.
    """

    def setUp(self):
        self.arbiter = DecisionArbiter(user_override_mode=SystemPolicyMode.PERFORMANCE)

    def test_scenario_nominal(self):
        """Scenario 1: All indicators nominal."""
        for name in self.arbiter.governors:
            self.arbiter.governors[name] = MockGovernor(
                capacity=90.0, risk=0.1, priority=self.arbiter.governors[name].priority,
                confidence=1.0, action=GovernorAction.NONE, reason="Nominal state", metrics={}
            )
        
        result = self.arbiter.assess_system()
        self.assertEqual(result["recommended_action"], GovernorAction.NONE)
        self.assertEqual(result["active_policy"], SystemPolicyMode.PERFORMANCE)
        self.assertEqual(result["max_risk_score"], 0.1)

    def test_scenario_thermal_spike(self):
        """Scenario 2: Thermal warning threshold exceeded (Immediate Safety Override)."""
        for name in self.arbiter.governors:
            self.arbiter.governors[name] = MockGovernor(
                capacity=90.0, risk=0.1, priority=self.arbiter.governors[name].priority,
                confidence=1.0, action=GovernorAction.NONE, reason="Nominal state", metrics={}
            )
            
        self.arbiter.governors["thermal"] = MockGovernor(
            capacity=15.0, risk=0.9, priority=100, confidence=1.0, action=GovernorAction.PAUSE,
            reason="Thermal spike to 85C", metrics={"temperature_c": 85.0}
        )
        
        result = self.arbiter.assess_system()
        self.assertEqual(result["recommended_action"], GovernorAction.PAUSE)
        self.assertEqual(result["active_policy"], SystemPolicyMode.ECO)
        self.assertEqual(result["worst_governor"], "thermal")
        self.assertEqual(result["max_risk_score"], 0.9)
        self.assertTrue(result["safety_override_triggered"])

    def test_scenario_low_battery(self):
        """Scenario 3: Battery critical (<10%) and discharging (Safety Override)."""
        for name in self.arbiter.governors:
            self.arbiter.governors[name] = MockGovernor(
                capacity=90.0, risk=0.1, priority=self.arbiter.governors[name].priority,
                confidence=1.0, action=GovernorAction.NONE, reason="Nominal state", metrics={}
            )
            
        self.arbiter.governors["battery"] = MockGovernor(
            capacity=8.0, risk=0.95, priority=90, confidence=1.0, action=GovernorAction.PAUSE,
            reason="Battery critical at 8%", metrics={"percent": 8.0, "power_plugged": False}
        )
        
        result = self.arbiter.assess_system()
        self.assertEqual(result["recommended_action"], GovernorAction.PAUSE)
        self.assertEqual(result["active_policy"], SystemPolicyMode.ECO)
        self.assertEqual(result["worst_governor"], "battery")
        self.assertTrue(result["safety_override_triggered"])

    def test_scenario_low_battery_eco(self):
        """Scenario 4: Battery low (15%) discharging -> ECO override."""
        for name in self.arbiter.governors:
            self.arbiter.governors[name] = MockGovernor(
                capacity=90.0, risk=0.1, priority=self.arbiter.governors[name].priority,
                confidence=1.0, action=GovernorAction.NONE, reason="Nominal state", metrics={}
            )
            
        self.arbiter.governors["battery"] = MockGovernor(
            capacity=15.0, risk=0.65, priority=90, confidence=1.0, action=GovernorAction.ECO,
            reason="Battery low at 15%", metrics={"percent": 15.0, "power_plugged": False}
        )
        
        result = self.arbiter.assess_system()
        self.assertEqual(result["recommended_action"], GovernorAction.ECO)
        self.assertEqual(result["active_policy"], SystemPolicyMode.ECO)
        self.assertEqual(result["worst_governor"], "battery")

    def test_scenario_multiple_warnings_precedence(self):
        """Scenario 5: CPU is elevated (ECO) but Memory is critical (PAUSE). PAUSE must override."""
        for name in self.arbiter.governors:
            self.arbiter.governors[name] = MockGovernor(
                capacity=90.0, risk=0.1, priority=self.arbiter.governors[name].priority,
                confidence=1.0, action=GovernorAction.NONE, reason="Nominal state", metrics={}
            )
            
        self.arbiter.governors["cpu"] = MockGovernor(
            capacity=40.0, risk=0.5, priority=60, confidence=1.0, action=GovernorAction.ECO,
            reason="CPU warning", metrics={}
        )
        self.arbiter.governors["memory"] = MockGovernor(
            capacity=5.0, risk=0.98, priority=95, confidence=1.0, action=GovernorAction.PAUSE,
            reason="Memory critical", metrics={}
        )
        
        result = self.arbiter.assess_system()
        self.assertEqual(result["recommended_action"], GovernorAction.PAUSE)
        self.assertEqual(result["active_policy"], SystemPolicyMode.ECO)
        self.assertEqual(result["worst_governor"], "memory")
        self.assertTrue(result["safety_override_triggered"])

    def test_scenario_degraded_battery_sensor(self):
        """Scenario 6: Degraded battery sensor (confidence=0.2) reporting critical level but ignored."""
        for name in self.arbiter.governors:
            self.arbiter.governors[name] = MockGovernor(
                capacity=90.0, risk=0.1, priority=self.arbiter.governors[name].priority,
                confidence=1.0, action=GovernorAction.NONE, reason="Nominal state", metrics={}
            )
            
        self.arbiter.governors["battery"] = MockGovernor(
            capacity=5.0, risk=0.95, priority=90, confidence=0.2, action=GovernorAction.PAUSE,
            reason="Battery reporting critical 5%", metrics={"percent": 5.0}
        )
        self.arbiter.governors["cpu"] = MockGovernor(
            capacity=40.0, risk=0.50, priority=60, confidence=1.0, action=GovernorAction.ECO,
            reason="CPU elevated", metrics={}
        )
        
        result = self.arbiter.assess_system()
        # Battery override should be bypassed due to low confidence (0.2 < 0.3)
        # CPU weighted vote ECO should dictate final decision
        self.assertEqual(result["recommended_action"], GovernorAction.ECO)
        self.assertEqual(result["active_policy"], SystemPolicyMode.ECO)
        self.assertFalse(result["safety_override_triggered"])

    def test_scenario_compound_weighted_eco(self):
        """Scenario 7: GPU is at 80% (ECO) and CPU is at 70% (ECO) -> Weighted average resolves to ECO."""
        for name in self.arbiter.governors:
            self.arbiter.governors[name] = MockGovernor(
                capacity=90.0, risk=0.1, priority=self.arbiter.governors[name].priority,
                confidence=1.0, action=GovernorAction.NONE, reason="Nominal state", metrics={}
            )
            
        self.arbiter.governors["cpu"] = MockGovernor(
            capacity=30.0, risk=0.55, priority=60, confidence=1.0, action=GovernorAction.ECO,
            reason="CPU ECO", metrics={}
        )
        self.arbiter.governors["gpu"] = MockGovernor(
            capacity=20.0, risk=0.60, priority=70, confidence=1.0, action=GovernorAction.ECO,
            reason="GPU ECO", metrics={}
        )
        
        result = self.arbiter.assess_system()
        self.assertEqual(result["recommended_action"], GovernorAction.ECO)
        self.assertEqual(result["active_policy"], SystemPolicyMode.ECO)
        self.assertFalse(result["safety_override_triggered"])

def run_simulation():
    print("="*60)
    print(" RG-Sim: RUNNING ARBITER SIMULATION HARNESS ")
    print("="*60)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestResourceGovernorSimulation)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if not res.wasSuccessful():
        sys.exit(1)

if __name__ == "__main__":
    run_simulation()
