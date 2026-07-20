from __future__ import annotations
import json
from typing import Any
from backend.core.memory.memory_store import MemoryStore

class SkillRegistry:
    @classmethod
    def register_skill(
        cls,
        skill_id: str,
        trigger_conditions: dict,
        prerequisites: dict,
        action_sequence: list[dict],
        confidence_score: float = 1.0,
        success_count: int = 1
    ) -> None:
        """Saves or updates a learned skill capability in the persistent database registry."""
        MemoryStore.add_skill(
            skill_id=skill_id,
            trigger_conditions=trigger_conditions,
            prerequisites=prerequisites,
            action_sequence=action_sequence,
            confidence_score=confidence_score,
            success_count=success_count
        )

    @classmethod
    def get_skill(cls, skill_id: str) -> dict | None:
        """Retrieves a specific skill by its ID, parsing database columns into dictionaries."""
        skills = MemoryStore.get_all_skills()
        for s in skills:
            if s["id"] == skill_id:
                return {
                    "skill_id": s["id"],
                    "trigger_conditions": json.loads(s["trigger_conditions_json"]),
                    "prerequisites": json.loads(s["prerequisites_json"]),
                    "action_sequence": json.loads(s["action_sequence_json"]),
                    "confidence_score": s["confidence_score"],
                    "success_count": s["success_count"]
                }
        return None

    @classmethod
    def get_matching_skills(cls, goal: str, context: dict | None = None) -> list[dict]:
        """Identifies skills whose trigger conditions match the current goal query."""
        skills = MemoryStore.get_all_skills()
        matched = []
        for s in skills:
            triggers = json.loads(s["trigger_conditions_json"])
            keywords = triggers.get("keywords", [])
            goal_lower = goal.lower()
            if any(k.lower() in goal_lower for k in keywords):
                matched.append({
                    "skill_id": s["id"],
                    "trigger_conditions": triggers,
                    "prerequisites": json.loads(s["prerequisites_json"]),
                    "action_sequence": json.loads(s["action_sequence_json"]),
                    "confidence_score": s["confidence_score"],
                    "success_count": s["success_count"]
                })
        return matched
