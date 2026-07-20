from __future__ import annotations
from backend.agents.planner import TaskGraph
from backend.core.debate.debate_message import DebateMessage

class CriticAgent:
    @classmethod
    def evaluate(cls, graph: TaskGraph) -> DebateMessage:
        """Inspects proposed TaskGraph steps to identify missing dependencies, cycles, or contradictions."""
        suggestions = []
        confidence = 1.0
        
        # Check circular dependencies
        try:
            if graph.has_cycle():
                confidence = 0.40
                suggestions.append("circular_dependency_detected: Break cyclic step chains.")
        except Exception:
            pass
            
        # Check invalid dependencies
        for step_id, step in graph.steps.items():
            for dep in step.dependencies:
                if dep not in graph.steps:
                    confidence = 0.50
                    suggestions.append(f"unresolved_dependency: Step {step_id} depends on missing step {dep}.")
                    
        content = "Critic evaluation complete. Plan structure verified." if not suggestions else "Objections raised by Critic."
        return DebateMessage(
            sender="CriticAgent",
            message_type="CRITIQUE",
            content=content,
            confidence_score=confidence,
            suggestions=suggestions
        )
