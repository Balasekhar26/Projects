"""Safety Review Layer (Layer 7).

Evaluates policy engine rules, risk classifiers (Risk Levels 0-5), path traversals,
and containment checks on the proposed execution plan.
"""

from __future__ import annotations

from typing import Any, Dict, List
from backend.core.safety import classify_risk, is_protected_path
from backend.core.risk_classifier import RiskClassifier


class SafetyReview:
    @classmethod
    def review(
        cls,
        execution_plan: Dict[str, Any],
        session_id: str,
        trust_tag: str = "SYSTEM_TRUST",
    ) -> Dict[str, Any]:
        """Evaluate risk levels and policy violations for planned operations in < 20 ms."""
        steps = execution_plan.get("steps", [])
        if not steps:
            return {
                "is_safe": True,
                "risk_level": 0,
                "rejection_reason": "",
            }

        classifier = RiskClassifier()
        max_risk_level = 0
        rejection_reason = ""
        is_safe = True

        for step in steps:
            tool_name = step.get("tool") or step.get("action") or ""
            args = step.get("args") or step.get("parameters") or {}

            # Resolve risk level for this tool
            risk_level = classifier.STATIC_RISK_MAP.get(tool_name, 1)

            if risk_level > max_risk_level:
                max_risk_level = risk_level

            # Check for Level 5 dangerous/prohibited actions
            if risk_level >= 5:
                is_safe = False
                rejection_reason = (
                    f"Prohibited dangerous action level 5 detected: '{tool_name}'."
                )
                break

            # Path Traversal & Protected Core Checks
            paths_to_check: list[str] = []
            if isinstance(args, dict):
                for k, v in args.items():
                    if isinstance(v, str) and ("/" in v or "\\" in v or "." in v):
                        paths_to_check.append(v)
            elif isinstance(args, str):
                paths_to_check.append(args)

            for p in paths_to_check:
                if ".." in p:
                    is_safe = False
                    rejection_reason = f"Path traversal attempt detected in path: '{p}'."
                    max_risk_level = 5
                    break

                if is_protected_path(p):
                    is_safe = False
                    rejection_reason = (
                        f"Modification of protected core file prohibited: '{p}'."
                    )
                    max_risk_level = 4
                    break

            if not is_safe:
                break

        # Double check using text-based check on description to capture metadata keywords
        plan_desc = str(execution_plan)
        text_decision = classify_risk(plan_desc, trust_tag=trust_tag)
        if text_decision.blocked:
            is_safe = False
            rejection_reason = text_decision.reason
            max_risk_level = 5

        return {
            "is_safe": is_safe,
            "risk_level": max_risk_level,
            "rejection_reason": rejection_reason,
        }
