"""Cognitive Kernel — Phase K9.5.

Acts as the central capability and routing kernel for Kattappa, coordinating
all system buses (Memory, Goals, Events, Context, Tools, Agents) to prevent
subsystem coupling.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Callable

from backend.core.cognitive_memory_bus import MEMORY_BUS
from backend.core.goal_hierarchy import GoalHierarchy
from backend.core.blackboard import BLACKBOARD

logger = logging.getLogger(__name__)


class MemoryBus:
    """Interface for Memory capabilities routing."""

    def read(
        self,
        query: str,
        memory_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Any]:
        return MEMORY_BUS.read(
            query, memory_types=memory_types, session_id=session_id, limit=limit
        )

    def write(
        self,
        memory_type: str,
        data: Dict[str, Any],
        confidence: float = 1.0,
        verified: bool = False,
    ) -> Any:
        return MEMORY_BUS.write(
            memory_type, data, confidence=confidence, verified=verified
        )


class GoalBus:
    """Interface for Goal and task hierarchy store routing."""

    def add_goal(
        self,
        node_id: str,
        parent_id: Optional[str],
        level: Any,
        title: str,
        description: Optional[str] = None,
        status: str = "PROPOSED",
        progress: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        # Resolves SQLite parent dirs automatically
        node = GoalHierarchy.add_node(
            node_id=node_id,
            parent_id=parent_id,
            level=level,
            title=title,
            description=description,
            status=status,
            progress=progress,
            metadata=metadata,
        )
        return node.id

    def update_status(
        self, node_id: str, status: str, progress: Optional[float] = None
    ) -> bool:
        from backend.core.goal_hierarchy import GoalHierarchy

        db = GoalHierarchy()
        return db.update_node(node_id, status=status, progress=progress)

    def get_progress(self, node_id: str) -> float:
        from backend.core.goal_hierarchy import GoalHierarchy

        node = GoalHierarchy.get_node(node_id)
        if node:
            return node.progress
        return 0.0


class EventBus:
    """Interface for global event pub/sub routing."""

    def publish(
        self,
        publisher: str,
        topic: str,
        payload: Dict[str, Any],
        confidence: float = 1.0,
    ) -> str:
        post = BLACKBOARD.publish(publisher, topic, payload, confidence=confidence)
        return post.post_id

    def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        BLACKBOARD.subscribe(topic, lambda post: callback(post.to_dict()))


class ContextBus:
    """Interface for routing execution contexts."""

    def build_context(self, session_id: str, query: str) -> Dict[str, Any]:
        from backend.core.context_manager import ContextManager

        return ContextManager.build_execution_context(session_id, query)


class ToolBus:
    """Interface for tool routing and reliability tracking."""

    def execute(self, tool_name: str, args: Dict[str, Any]) -> Any:
        # Executes tool and logs reliability metrics
        from backend.core.tool_reliability import ToolReliabilityTracker

        # In a real system, imports ToolExecutorAgent
        # Here we mock tool reliability log
        success = True
        error_msg = None
        latency = 0.05
        try:
            # Look up execution pathway
            if tool_name == "calculator":
                val = eval(str(args.get("expr", "0")))
                return {"result": val}
            return {"result": f"Executed tool {tool_name} successfully"}
        except Exception as e:
            success = False
            error_msg = str(e)
            raise e
        finally:
            try:
                ToolReliabilityTracker.record_invocation(
                    tool_name, success, latency, error_msg
                )
            except Exception:
                pass


class AgentBus:
    """Interface for agent registry and execution graph routing."""

    def get_agent(self, agent_name: str) -> Any:
        from backend.core.orchestrator.registry import ORCHESTRATOR_REGISTRY

        return ORCHESTRATOR_REGISTRY.get(agent_name)

    def schedule_task(self, task: Any, context: Any) -> Any:
        from backend.core.orchestrator.scheduler import TaskScheduler

        # Schedule via default task scheduler
        scheduler = TaskScheduler()
        return scheduler._execute_task(task, "direct-kernel-task", context)


class CognitiveKernel:
    """The central K9.5 Cognitive Operating System kernel coordinator."""

    _instance: Optional[CognitiveKernel] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        from backend.core.cos.executive_controller import CONTROLLER

        self.memory = MemoryBus()
        self.goals = GoalBus()
        self.events = EventBus()
        self.context = ContextBus()
        self.tools = ToolBus()
        self.agents = AgentBus()
        self.executive = CONTROLLER
        self._initialized = True


# Global Kernel Singleton reference
KERNEL = CognitiveKernel()
