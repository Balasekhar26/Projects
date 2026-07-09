"""Skill Discovery Engine (Program 55.0).

Enables dynamic search, dependency checks, and trust-based ranking
of executable skills based on target task objectives and available platform tools.
"""
from __future__ import annotations

from typing import Any, Dict, List

from backend.core.skill_graph import SkillGraph
from backend.core.skill_library import SkillLibrary


class SkillDiscoveryEngine:
    """Coordinates semantic searches and prerequisite validations to discover optimal skills."""

    @classmethod
    def discover_skills(cls, goal_text: str, available_tools: List[str]) -> List[Dict[str, Any]]:
        """Finds, validates, and ranks candidate skills matching goal text description."""
        # 1. Query SkillLibrary search index
        candidates = SkillLibrary.search(goal_text)
        if not candidates:
            return []

        scored_candidates = []

        # 2. Score and check prerequisites for each candidate
        for skill in candidates:
            skill_id = skill.get("id")
            skill_name = skill["name"]
            
            # Retrieve detailed graph information if available
            details = SkillGraph.get_skill_details(skill_id)
            if details is None:
                # Fallback: check if skill name matches directly in graph
                details = SkillGraph.get_skill_details(skill_name.lower())

            # Prerequisite tool validation
            if details:
                prereqs_met = SkillGraph.verify_skill_prerequisites_met(
                    details["skill_id"], available_tools
                )
            else:
                # Fallback: check if skill tags (which map to required tools) are a subset of available tools
                required = set(skill.get("tags") or [])
                available = set(available_tools)
                prereqs_met = required.issubset(available)

            trust_priority = 1 if skill.get("trust") == "trusted" else 0
            success_rate = skill.get("success_rate") or 0.0

            scored_candidates.append({
                "skill": skill,
                "prereqs_met": prereqs_met,
                "trust_priority": trust_priority,
                "success_rate": success_rate,
            })

        # 3. Multi-tier ranking
        # Sorts by:
        # 1) prerequisites fully met (True first)
        # 2) trust tier (trusted first)
        # 3) success rate (higher first)
        # 4) name (alphabetical)
        scored_candidates.sort(
            key=lambda c: (
                not c["prereqs_met"],
                -c["trust_priority"],
                -c["success_rate"],
                c["skill"]["name"],
            )
        )

        return [c["skill"] for c in scored_candidates]
