"""Council Debate Layer (Layer 5).

Orchestrates Personality Council session, tabulates votes, and runs process arbiter rules.
"""

from __future__ import annotations

import time
from typing import Any, Dict
from backend.core.council_session import CouncilSession


class CouncilDebate:
    @classmethod
    def debate(
        cls,
        attention_frame: Dict[str, Any],
        memory_payload: Dict[str, Any],
        reasoning_hypothesis: str,
    ) -> Dict[str, Any]:
        """Orchestrates Personality Council session on a reasoning hypothesis."""
        clean_message = attention_frame.get("clean_message", "")
        intent_type = attention_frame.get("intent_type", "general")

        # Build context metadata payload for the council
        context = {
            "memory": memory_payload,
            "reasoning_hypothesis": reasoning_hypothesis,
            "attention": attention_frame,
        }

        # Set code change or production triggers based on intent/focus
        code_change = (
            "code" in attention_frame.get("focus_keywords", [])
            or "coder" in clean_message.lower()
        )
        production = any(
            kw in clean_message.lower()
            for kw in ["delete", "rm", "production", "db", "drop", "truncate"]
        )

        try:
            # For complex/risky tasks, use full deliberation; otherwise, quick_deliberate (top N)
            if attention_frame.get("complexity_level", 1) > 1 or production:
                res = CouncilSession.deliberate(
                    question=clean_message,
                    question_type=intent_type,
                    context=context,
                    code_change=code_change,
                    production=production,
                )
            else:
                res = CouncilSession.quick_deliberate(
                    question=clean_message,
                    question_type=intent_type,
                    context=context,
                    n=3,
                    code_change=code_change,
                    production=production,
                )
        except Exception as exc:
            # Fallback in case of runtime deliberation failure
            return {
                "votes": [],
                "consensus_strength": 0.0,
                "status": "escalate",
                "dissent": [],
                "reasons": [f"Council deliberation failed: {exc}"],
                "requires_human_approval": True,
                "arbiter_findings": [],
            }

        d = res.to_dict()

        # Calculate consensus strength
        total_mass = res.approve_mass + res.reject_mass
        consensus_strength = (
            (res.approve_mass / total_mass) if total_mass > 0 else 0.0
        )

        return {
            "votes": d.get("votes", []),
            "consensus_strength": consensus_strength,
            "status": d.get("consensus_status", "escalate"),
            "dissent": d.get("dissent", []),
            "reasons": d.get("reasons", []),
            "requires_human_approval": d.get("requires_human_approval", False),
            "arbiter_findings": d.get("arbiter_findings", []),
        }
