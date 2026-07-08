from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class GoalCreatedPayload:
    goal_id: str
    description: str
    priority: float
    dependencies: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "description": self.description,
            "priority": self.priority,
            "dependencies": self.dependencies,
        }


@dataclass(frozen=True)
class IntentClassifiedPayload:
    intent: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class MemoryRetrievedPayload:
    query: str
    results: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "results": self.results,
        }


@dataclass(frozen=True)
class ToolExecutedPayload:
    tool_name: str
    arguments: Dict[str, Any]
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "success": self.success,
            "result": self.result,
            "error": self.error,
        }
