"""Mission World State Tracker (Program 24.0).

Monitors external environmental assertions and assumptions between stage execution checkpoints.
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MissionWorldStateTracker:
    """Audits environmental constraints (networks, paths, process tables) to ensure run assumptions hold."""

    @classmethod
    def verify_assumption(cls, assumption_type: str, parameter: str) -> bool:
        """Verifies a single environmental assumption by executing local checks.

        Supported types:
            - "FILE_EXISTS": checks path existence.
            - "PING_REACHABLE": checks host ping.
            - "ENV_VAR": checks environment variable presence.
        """
        if assumption_type == "FILE_EXISTS":
            res = os.path.exists(parameter)
            logger.info("MissionWorldStateTracker: Verification FILE_EXISTS on '%s' -> %s", parameter, res)
            return res
            
        elif assumption_type == "PING_REACHABLE":
            try:
                # Run single ping check
                cmd = ["ping", "-n", "1", parameter] if os.name == "nt" else ["ping", "-c", "1", parameter]
                res_code = subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0)
                verified = (res_code == 0)
                logger.info("MissionWorldStateTracker: Verification PING_REACHABLE on '%s' -> %s", parameter, verified)
                return verified
            except Exception:
                return False

        elif assumption_type == "ENV_VAR":
            res = parameter in os.environ
            logger.info("MissionWorldStateTracker: Verification ENV_VAR on '%s' -> %s", parameter, res)
            return res

        logger.warning("MissionWorldStateTracker: Unknown assumption type '%s'", assumption_type)
        return True

    @classmethod
    def verify_all_assumptions(cls, assumptions: List[Dict[str, str]]) -> Dict[str, Any]:
        """Audits a list of assumption blocks, flagging any invalid checks."""
        invalid_assumptions = []
        
        for asm in assumptions:
            asm_type = asm.get("type", "")
            param = asm.get("param", "")
            if not cls.verify_assumption(asm_type, param):
                invalid_assumptions.append(asm)

        passed = len(invalid_assumptions) == 0
        return {
            "passed": passed,
            "invalid_assumptions": invalid_assumptions
        }
