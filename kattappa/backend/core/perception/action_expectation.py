"""Action Expectation (Program 18.1).

Declares expected side-effects and layout constraints for visual UI operations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ActionExpectation:
    """Defines what changes are expected in the UI state after executing an action."""
    expected_url: Optional[str] = None
    expected_text_present: List[str] = field(default_factory=list)
    expected_text_absent: List[str] = field(default_factory=list)
    expected_new_elements: List[str] = field(default_factory=list)
    max_wait_ms: int = 1000

    def evaluate_match(self, observed_texts: List[str], current_url: Optional[str] = None) -> float:
        """Evaluates how well the observed state meets these expectations.

        Returns match rating score [0.0 - 1.0].
        """
        score_weight = 0.0
        passed_weight = 0.0

        # 1. URL Check
        if self.expected_url:
            score_weight += 1.0
            if current_url and self.expected_url in current_url:
                passed_weight += 1.0

        # 2. Expected Text Presence Check
        if self.expected_text_present:
            score_weight += len(self.expected_text_present)
            observed_lower = [t.lower() for t in observed_texts]
            for text in self.expected_text_present:
                # check substring match anywhere
                if any(text.lower() in obs for obs in observed_lower):
                    passed_weight += 1.0

        # 3. Expected Text Absence Check
        if self.expected_text_absent:
            score_weight += len(self.expected_text_absent)
            observed_lower = [t.lower() for t in observed_texts]
            for text in self.expected_text_absent:
                if not any(text.lower() in obs for obs in observed_lower):
                    passed_weight += 1.0

        if score_weight == 0.0:
            return 1.0

        return passed_weight / score_weight


# Default expectations catalog for browser and desktop routines
EXPECTATION_REGISTRY: Dict[str, ActionExpectation] = {
    "BROWSER_CLICK": ActionExpectation(
        expected_text_absent=["error", "failed to connect", "not found"],
        max_wait_ms=1500
    ),
    "BROWSER_NAVIGATE": ActionExpectation(
        expected_text_absent=["404", "error", "connection timed out"],
        max_wait_ms=2000
    ),
    "DESKTOP_CLICK": ActionExpectation(
        expected_text_absent=["crash", "not responding"],
        max_wait_ms=1000
    )
}


def get_expectation_for_action(action: str, params: Dict[str, Any]) -> ActionExpectation:
    """Finds or builds custom expectations for a given action payload."""
    action_upper = action.upper()
    default_exp = EXPECTATION_REGISTRY.get(action_upper)
    
    # Extract dynamic expectations from params if present
    custom_present = params.get("expect_text_present") or params.get("expected_text")
    custom_absent = params.get("expect_text_absent")
    custom_url = params.get("expect_url")

    # Build dynamically if custom fields exist
    if custom_present or custom_absent or custom_url:
        present_list = [custom_present] if isinstance(custom_present, str) else (custom_present or [])
        absent_list = [custom_absent] if isinstance(custom_absent, str) else (custom_absent or [])
        return ActionExpectation(
            expected_url=custom_url,
            expected_text_present=present_list,
            expected_text_absent=absent_list,
            max_wait_ms=params.get("expect_timeout_ms", 1000)
        )

    if default_exp:
        return default_exp

    # Fallback default empty expectation
    return ActionExpectation()
