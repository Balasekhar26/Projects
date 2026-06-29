from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class ECLPolicyEngine:
    """Enforces execution boundaries, compliance rules, and safety overrides for the ECL."""

    @classmethod
    def validate_plan(
        cls,
        goal_title: str,
        tasks: List[Dict[str, Any]],
    ) -> Tuple[bool, str | None]:
        """Validates all decomposed steps against KOS safety policies.

        Returns (is_valid, violation_reason).
        """
        text = (goal_title + " " + " ".join(t.get("title", "") + " " + t.get("description", "") for t in tasks)).lower()

        # Rule 1: Prevent unverified broad deletions
        if any(w in text for w in ["rm -rf", "delete all", "wipe", "drop database"]):
            reason = "Violated policy: Absolute command line execution boundaries. Unverified broad deletion prohibited."
            logger.warning(reason)
            return False, reason

        # Rule 2: Gated self-modification protection
        if "modify self" in text or "override kernel" in text:
            reason = "Violated policy: Self-modification restriction. Overriding executive core state requires manual approval."
            logger.warning(reason)
            return False, reason

        # Rule 3: Network isolation limits
        if "bypass firewall" in text or "disable egress rules" in text:
            reason = "Violated policy: Egress traffic isolation rules. Bypassing network safety limits is prohibited."
            logger.warning(reason)
            return False, reason

        return True, None
