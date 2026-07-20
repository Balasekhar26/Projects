from __future__ import annotations
from backend.agents.planner import TaskGraph
from backend.core.debate.debate_message import DebateMessage

class ResourceAgent:
    @classmethod
    def evaluate(cls, graph: TaskGraph) -> DebateMessage:
        """Audits memory constraints and hardware limitations (such as 12GB RAM limitations)."""
        suggestions = []
        confidence = 1.0
        
        for step_id, step in graph.steps.items():
            params = step.params or {}
            model_name = str(params.get("model", "")).lower()
            
            # Reject models exceeding laptop capacities
            if "72b" in model_name or "70b" in model_name or "110b" in model_name:
                confidence = min(confidence, 0.40)
                suggestions.append(f"insufficient_ram: Model size {model_name} exceeds 12GB host memory budget.")
                
        content = "Resource evaluation complete. Host memory limits satisfied." if not suggestions else "Memory limit violations detected."
        return DebateMessage(
            sender="ResourceAgent",
            message_type="CRITIQUE",
            content=content,
            confidence_score=confidence,
            suggestions=suggestions
        )
