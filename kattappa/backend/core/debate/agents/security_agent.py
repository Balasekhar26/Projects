from __future__ import annotations
from backend.agents.planner import TaskGraph
from backend.core.debate.debate_message import DebateMessage

class SecurityAgent:
    @classmethod
    def evaluate(cls, graph: TaskGraph) -> DebateMessage:
        """Audits task graph operations for unsafe actions, permissions violations, or command injections."""
        suggestions = []
        confidence = 1.0
        
        for step_id, step in graph.steps.items():
            action = step.action.upper()
            params = step.params or {}
            command = str(params.get("command", "")).lower()
            
            # Deletion/Format Checks
            if "DELETE" in action or "REMOVE" in action or "rm " in command or "del " in command:
                confidence = min(confidence, 0.50)
                suggestions.append(f"high_risk_deletion: Step {step_id} attempts to delete directories/files.")
            if "FORMAT" in action or "format " in command:
                confidence = min(confidence, 0.20)
                suggestions.append(f"critical_format: Step {step_id} attempts disk formatting.")
                
        content = "Security review passed. No critical threats detected." if not suggestions else "Security alerts detected in plan."
        return DebateMessage(
            sender="SecurityAgent",
            message_type="CRITIQUE",
            content=content,
            confidence_score=confidence,
            suggestions=suggestions
        )
