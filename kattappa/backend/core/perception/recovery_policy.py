"""Recovery Policy (Program 18.1).

Determines recovery actions (retry, dismiss popup, or replan) based on visual layout differences.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class RecoveryPolicy:
    """Evaluates state mismatch severity and outlines automatic mitigation vectors."""

    @classmethod
    def evaluate_recovery(
        cls,
        action: str,
        params: Dict[str, Any],
        diff_data: Dict[str, Any],
        score: float
    ) -> Dict[str, Any]:
        """Maps layout diff metrics to a recovery strategy.

        Returns decision dictionary:
            {
                "recovery_action": str,  # RETRY | DISMISS_MODAL | HUMAN_APPROVAL | REPLAN
                "message": str
            }
        """
        # Case 1: Unexpected modal opened (like an alert dialog blocking execution)
        if diff_data.get("modal_opened"):
            logger.info("RecoveryPolicy: Modal dialog blocked execution for %s.", action)
            return {
                "recovery_action": "DISMISS_MODAL",
                "message": "An unexpected popup block was encountered. Emitting cancel action."
            }

        # Case 2: Transient/Partial failures (low score but not totally refuted, e.g. text elements loading slowly)
        if 0.5 <= score < 0.9:
            logger.info("RecoveryPolicy: Transient layout mismatch (score %.2f). Recommending retry.", score)
            return {
                "recovery_action": "RETRY",
                "message": f"Action output did not fully satisfy expectations (score: {score}). Retrying action."
            }

        # Case 3: Major failure (e.g. error banners appeared, or critical nodes disappeared)
        critical_error_indicators = ["access denied", "unauthorized", "fatal error", "404 not found"]
        added_lower = [t.lower() for t in diff_data.get("added_texts", [])]
        
        has_critical_error = any(any(err in text for err in critical_error_indicators) for text in added_lower)
        if has_critical_error:
            logger.warning("RecoveryPolicy: Critical security or system error detected. Forcing replan.")
            return {
                "recovery_action": "REPLAN",
                "message": "Critical system or security exception was detected on the interface."
            }

        # Default fallback: Replan
        logger.warning("RecoveryPolicy: Execution expectation failed completely (score %.2f). Initiating replanner.", score)
        return {
            "recovery_action": "REPLAN",
            "message": "Execution results did not meet visual constraints. Forcing goal replanning."
        }
