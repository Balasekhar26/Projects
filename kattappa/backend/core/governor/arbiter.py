from typing import Dict, Any, List
from enum import Enum

from backend.core.governor.base import BaseGovernor, GovernorAction
from backend.core.governor.cpu import CpuGovernor
from backend.core.governor.gpu import GpuGovernor
from backend.core.governor.memory import MemoryGovernor
from backend.core.governor.thermal import ThermalGovernor
from backend.core.governor.battery import BatteryGovernor
from backend.core.governor.network import NetworkGovernor
from backend.core.governor.disk import DiskGovernor
from backend.core.governor.latency import LatencyGovernor
from backend.core.governor.event_bus import EventBus

class SystemPolicyMode(str, Enum):
    ECO = "eco"
    BALANCED = "balanced"
    PERFORMANCE = "performance"
    MAXIMUM = "maximum"

class DecisionArbiter:
    """
    The central intelligence that queries all individual governors,
    consolidates their recommended actions, and selects the safest policy mode.
    Enforces the Safety Override priority hierarchy and Weighted Voting for other metrics.
    """
    
    def __init__(self, user_override_mode: SystemPolicyMode = SystemPolicyMode.PERFORMANCE):
        self.governors: Dict[str, BaseGovernor] = {
            "cpu": CpuGovernor(),
            "gpu": GpuGovernor(),
            "memory": MemoryGovernor(),
            "thermal": ThermalGovernor(),
            "battery": BatteryGovernor(),
            "network": NetworkGovernor(),
            "disk": DiskGovernor(),
            "latency": LatencyGovernor()
        }
        self.user_override_mode = user_override_mode
        self.event_bus = EventBus()

    def assess_system(self) -> Dict[str, Any]:
        """
        Polls all governors and returns the aggregate system decision,
        publishing updates to the Event Bus.
        """
        results = {}
        for name, gov in self.governors.items():
            try:
                results[name] = gov.assess()
            except Exception as e:
                # Safe fallback on governor failure
                results[name] = {
                    "available_capacity": 0.0,
                    "risk_score": 1.0,
                    "priority": gov.priority,
                    "confidence": 0.0,
                    "recommended_action": GovernorAction.PAUSE,
                    "reason": f"Governor exception: {e}",
                    "metrics": {}
                }

        # 1. Check for Safety Overrides
        # Priority >= 90 is critical (Thermal, Memory, Battery)
        safety_override_triggered = False
        override_action = GovernorAction.NONE
        worst_governor = None
        highest_priority = -1
        max_risk_score = 0.0

        for name, res in results.items():
            priority = res["priority"]
            confidence = res.get("confidence", 1.0)
            act = res["recommended_action"]
            risk = res["risk_score"]

            if risk > max_risk_score:
                max_risk_score = risk

            if priority >= 90 and confidence >= 0.3:
                # Critical safety governor wants to throttle/pause/shutdown
                if act in (GovernorAction.PAUSE, GovernorAction.SHUTDOWN, GovernorAction.ECO):
                    # Enforce precedence of override action
                    action_precedence = [GovernorAction.SHUTDOWN, GovernorAction.PAUSE, GovernorAction.ECO, GovernorAction.NONE]
                    if action_precedence.index(act) < action_precedence.index(override_action):
                        override_action = act
                        worst_governor = name
                        highest_priority = priority
                        safety_override_triggered = True

        # 2. If no Safety Override is triggered, run Weighted Voting on other dimensions
        if safety_override_triggered:
            final_action = override_action
            reason = f"Safety override triggered by critical governor '{worst_governor}': {results[worst_governor]['reason']}"
        else:
            action_map = {
                GovernorAction.NONE: 0,
                GovernorAction.ECO: 1,
                GovernorAction.PAUSE: 2,
                GovernorAction.SHUTDOWN: 3
            }
            rev_action_map = {0: GovernorAction.NONE, 1: GovernorAction.ECO, 2: GovernorAction.PAUSE, 3: GovernorAction.SHUTDOWN}

            total_weight = 0.0
            weighted_risk = 0.0
            
            # Count only active (non-NONE) votes for action selection
            active_weight = 0.0
            active_action_val = 0.0

            for name, res in results.items():
                act = res["recommended_action"]
                risk = res["risk_score"]
                priority = res["priority"]
                confidence = res.get("confidence", 1.0)

                weight = priority * confidence
                if weight > 0.0:
                    total_weight += weight
                    weighted_risk += risk * weight
                    
                    if act != GovernorAction.NONE:
                        active_weight += weight
                        active_action_val += action_map[act] * weight

            if total_weight > 0.0:
                avg_risk = weighted_risk / total_weight
                max_risk_score = avg_risk
                
                if active_weight > 0.0:
                    avg_action_val = active_action_val / active_weight
                    nearest_action_val = round(avg_action_val)
                    final_action = rev_action_map.get(nearest_action_val, GovernorAction.NONE)
                else:
                    final_action = GovernorAction.NONE

                # Find the governor that matches the highest risk/vote among trusted sensors (confidence >= 0.3)
                highest_gov_risk = -1.0
                for name, res in results.items():
                    if res.get("confidence", 1.0) >= 0.3 and res["risk_score"] > highest_gov_risk:
                        highest_gov_risk = res["risk_score"]
                        worst_governor = name
                        highest_priority = res["priority"]
                
                reason = "Weighted decision calculated across nominal/elevated indicators."
            else:
                final_action = GovernorAction.NONE
                max_risk_score = 0.0
                worst_governor = "none"
                highest_priority = 1
                reason = "No active sensor inputs available."

        # 3. Map final action and user override to actual active policy mode
        active_policy = SystemPolicyMode.PERFORMANCE
        
        if final_action == GovernorAction.SHUTDOWN:
            active_policy = SystemPolicyMode.ECO
        elif final_action == GovernorAction.PAUSE:
            active_policy = SystemPolicyMode.ECO
        elif final_action == GovernorAction.ECO:
            active_policy = SystemPolicyMode.ECO
        else:
            # Nominal system state: respect user override
            active_policy = self.user_override_mode

        decision = {
            "recommended_action": final_action,
            "active_policy": active_policy,
            "worst_governor": worst_governor,
            "max_risk_score": round(max_risk_score, 2),
            "priority": highest_priority,
            "safety_override_triggered": safety_override_triggered,
            "reason": reason,
            "governor_details": results
        }

        # 4. Decoupled telemetry: publish to the Event Bus
        self.event_bus.publish("governor/decision", decision)

        return decision
