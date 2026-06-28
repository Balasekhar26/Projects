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

class SystemPolicyMode(str, Enum):
    ECO = "eco"
    BALANCED = "balanced"
    PERFORMANCE = "performance"
    MAXIMUM = "maximum"

class DecisionArbiter:
    """
    The central intelligence that queries all individual governors,
    consolidates their recommended actions, and selects the safest policy mode.
    Enforces the 'most conservative vote wins' strategy.
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

    def assess_system(self) -> Dict[str, Any]:
        """
        Polls all governors and returns the aggregate system decision.
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
                    "priority": 10,
                    "recommended_action": GovernorAction.PAUSE,
                    "reason": f"Governor exception: {e}",
                    "metrics": {}
                }

        # 1. Determine aggregate action based on the "most conservative vote wins" rule
        action_precedence = [GovernorAction.SHUTDOWN, GovernorAction.PAUSE, GovernorAction.ECO, GovernorAction.NONE]
        
        final_action = GovernorAction.NONE
        worst_governor = None
        highest_priority = -1
        max_risk_score = 0.0
        
        for name, res in results.items():
            act = res["recommended_action"]
            risk = res["risk_score"]
            priority = res["priority"]
            
            # Find max risk score
            if risk > max_risk_score:
                max_risk_score = risk
            
            # Precedence check
            curr_idx = action_precedence.index(act)
            best_idx = action_precedence.index(final_action)
            
            if curr_idx < best_idx:
                final_action = act
                worst_governor = name
                highest_priority = priority
            elif curr_idx == best_idx and priority > highest_priority:
                worst_governor = name
                highest_priority = priority

        # 2. Map final action and user override to actual active policy mode
        # User override sets a ceiling of what is allowed
        # (e.g. if override is ECO, we never run PERFORMANCE/MAXIMUM, even if governors are nomimal)
        active_policy = SystemPolicyMode.PERFORMANCE
        
        if final_action == GovernorAction.SHUTDOWN:
            active_policy = SystemPolicyMode.ECO  # Fallback to absolute minimum
        elif final_action == GovernorAction.PAUSE:
            active_policy = SystemPolicyMode.ECO  # Pause workflows
        elif final_action == GovernorAction.ECO:
            active_policy = SystemPolicyMode.ECO
        else:
            # Nominal system state: respect user override
            active_policy = self.user_override_mode

        return {
            "recommended_action": final_action,
            "active_policy": active_policy,
            "worst_governor": worst_governor,
            "max_risk_score": round(max_risk_score, 2),
            "priority": highest_priority,
            "governor_details": results
        }
