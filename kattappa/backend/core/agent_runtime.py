"""Agent Runtime (Program 51.0).

Defines running Agent instances wrapping declarative AgentDefinitions, connecting
them directly to the EventBus, CognitiveBlackboard, GoalManager, and ExecutionSandbox.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional, Set

from backend.core.agent_registry import AgentDefinition
from backend.core.blackboard import BLACKBOARD, BlackboardPost
from backend.core.event_bus import EventBus, Event, EventName
from backend.core.goal_manager import GoalManager
from backend.core.sandbox.local_sandbox import LocalExecutionSandbox


class Agent:
    """A live executing agent specialist wrapping core platform abstractions."""

    def __init__(self, definition: AgentDefinition, execution_budget: float = 1000.0) -> None:
        self.agent_id = f"agt_{uuid.uuid4().hex[:8]}"
        self.name = definition.name
        self.role = definition.purpose
        self.capabilities: Set[str] = set(definition.tools)
        self.authority_level = definition.priority
        self.execution_budget = execution_budget
        self.confidence = 1.0

    def publish_to_blackboard(
        self,
        topic: str,
        payload: Dict[str, Any],
        confidence: Optional[float] = None,
    ) -> BlackboardPost:
        """Publishes observations or insights to the global Blackboard and emits event bus signal."""
        active_confidence = confidence if confidence is not None else self.confidence
        post = BLACKBOARD.publish(
            publisher=self.name,
            topic=topic,
            payload=payload,
            confidence=active_confidence,
        )

        # Notify general event bus
        EventBus.publish(
            event_name=EventName.BELIEF_UPDATED,
            payload={"post_id": post.post_id, "topic": topic, "publisher": self.name},
            source=self.name,
        )

        return post

    def subscribe_to_event(self, event_name: str, callback: Callable[[Event], None]) -> None:
        """Subscribes agent callbacks to target EventBus event streams."""
        EventBus.subscribe(event_name, callback)

    def request_goal(
        self,
        title: str,
        description: Optional[str] = None,
        parent_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Requests creation of a task/subgoal via GoalManager and emits event notification."""
        goal = GoalManager.add_goal(
            title=title,
            description=description,
            parent_id=parent_id,
            depends_on=depends_on,
            owner_agent=self.name,
        )

        # Notify general event bus
        EventBus.publish(
            event_name=EventName.GOAL_CREATED,
            payload={"goal_id": goal["goal_id"], "title": title, "owner_agent": self.name},
            source=self.name,
        )

        return goal

    def invoke_sandbox_action(
        self,
        cmd: List[str],
        timeout: float = 10.0,
        cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes a command inside the LocalExecutionSandbox and logs start/end outcomes."""
        # Notify execution started
        EventBus.publish(
            event_name=EventName.EXECUTION_STARTED,
            payload={"command": cmd, "agent_name": self.name},
            source=self.name,
        )

        res = LocalExecutionSandbox.execute_sandboxed_command(
            cmd=cmd,
            timeout=timeout,
            cwd=cwd,
            enable_rollback=True,
        )

        # Notify outcome
        success = res["returncode"] == 0
        EventBus.publish(
            event_name=EventName.EXECUTION_FINISHED if success else EventName.EXECUTION_FAILED,
            payload={
                "command": cmd,
                "agent_name": self.name,
                "returncode": res["returncode"],
                "rolled_back": res["rolled_back"],
            },
            source=self.name,
        )

        return res
