from typing import Dict, Any, Optional
from backend.core.governor.arbiter import DecisionArbiter, SystemPolicyMode, GovernorAction

class RuntimeScheduler:
    """
    Coordinates with the Decision Arbiter to adjust execution parameters
    dynamically (active workers, context caps, batch size, pauses) based
    on physical system headroom.
    """
    
    def __init__(self, arbiter: Optional[DecisionArbiter] = None):
        self.arbiter = arbiter or DecisionArbiter()

    def get_execution_limits(self) -> Dict[str, Any]:
        """
        Retrieves the recommended dynamic resource limits based on current system pressure.
        """
        assessment = self.arbiter.assess_system()
        policy = assessment["active_policy"]
        action = assessment["recommended_action"]

        # Default limits
        max_workers = 4
        context_len = 2048
        microbatch = 2
        should_pause = False

        if action in (GovernorAction.PAUSE, GovernorAction.SHUTDOWN):
            should_pause = True
            max_workers = 1
            context_len = 256
            microbatch = 1
        elif policy == SystemPolicyMode.ECO:
            max_workers = 1
            context_len = 512
            microbatch = 1
        elif policy == SystemPolicyMode.BALANCED:
            max_workers = 2
            context_len = 1024
            microbatch = 1
        elif policy == SystemPolicyMode.PERFORMANCE:
            max_workers = 4
            context_len = 2048
            microbatch = 2
        elif policy == SystemPolicyMode.MAXIMUM:
            max_workers = 8
            context_len = 2048
            microbatch = 4

        return {
            "policy_mode": policy,
            "recommended_action": action,
            "should_pause": should_pause,
            "max_workers": max_workers,
            "context_length_cap": context_len,
            "microbatch_limit": microbatch,
            "worst_governor": assessment["worst_governor"],
            "max_risk_score": assessment["max_risk_score"]
        }
