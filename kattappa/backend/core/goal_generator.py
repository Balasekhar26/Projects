from __future__ import annotations
from typing import Any, Dict, List
from backend.planner.goal_stack import GoalItem

class GoalGenerator:
    """Translates classified user intents into structured compound and primitive task goals."""

    @staticmethod
    def generate_goals(intent_data: Dict[str, Any]) -> List[GoalItem]:
        intent = intent_data.get("intent", "general_task")
        goals = []

        if intent == "schedule_meeting":
            goals.append(GoalItem(
                goal_id="goal-meeting",
                name="schedule_meeting",
                priority="HIGH",
                utility_score=90.0,
                hard_constraints={"timeout": 30.0}
            ))
        elif intent == "install_software":
            goals.append(GoalItem(
                goal_id="goal-install",
                name="install_software",
                priority="HIGH",
                utility_score=95.0,
                hard_constraints={"timeout": 120.0}
            ))
        elif intent == "verify_installation":
            goals.append(GoalItem(
                goal_id="goal-verify",
                name="verify_installation",
                priority="MEDIUM",
                utility_score=80.0,
                hard_constraints={"timeout": 15.0}
            ))
        elif intent == "summarize_logs":
            # For log summary, HTN task sequences
            goals.append(GoalItem(
                goal_id="goal-logs",
                name="compile_code",
                priority="MEDIUM",
                utility_score=85.0
            ))
        else:
            goals.append(GoalItem(
                goal_id="goal-fallback",
                name="compile_code",
                priority="LOW",
                utility_score=50.0
            ))

        return goals
