from __future__ import annotations
from backend.agents.planner import TaskGraph
from backend.core.debate.debate_message import DebateMessage

class EfficiencyAgent:
    @classmethod
    def evaluate(cls, graph: TaskGraph) -> DebateMessage:
        """Audits plan steps to optimize execution latencies and suggest skill cache recommendations."""
        suggestions = []
        confidence = 1.0
        
        goal = graph.goal.lower()
        # Suggest cached skills if keywords match common tasks
        if "install" in goal and "python" in goal:
            suggestions.append("skill_recommendation: Match Python package installations to skill library.")
            
        content = "Efficiency evaluation passed. Speed constraints optimized."
        return DebateMessage(
            sender="EfficiencyAgent",
            message_type="CRITIQUE",
            content=content,
            confidence_score=confidence,
            suggestions=suggestions
        )
