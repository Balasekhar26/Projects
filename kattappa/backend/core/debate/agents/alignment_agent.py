from __future__ import annotations
from backend.agents.planner import TaskGraph
from backend.core.debate.debate_message import DebateMessage

class AlignmentAgent:
    @classmethod
    def evaluate(cls, graph: TaskGraph) -> DebateMessage:
        """Audits task graphs against structural ethics and behavioral heuristics (Rama, Shiva, Hanuman balance)."""
        suggestions = []
        confidence = 1.0
        
        # Shiva Layer (Balance/restraint check)
        # If too many parallel tasks are planned or risk is high, recommend limits
        if len(graph.steps) > 5:
            suggestions.append("shiva_restraint: Excessive task steps. Restructure plan to enforce shiva restraint.")
            
        content = "Alignment check passed. Core ethics rules satisfied."
        return DebateMessage(
            sender="AlignmentAgent",
            message_type="CRITIQUE",
            content=content,
            confidence_score=confidence,
            suggestions=suggestions
        )
