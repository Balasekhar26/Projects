"""Stateful Execution Engine Orchestration (Program 5G-6).

Coordinative loop managing plan executions, thread/task runs, events, retries,
rollbacks, and crash checkpoints.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.core.execution.checkpoints import CheckpointManager
from backend.core.execution.events import (
    EventBus,
    TaskStartedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
)
from backend.core.execution.execution_state import (
    ExecutionContext,
    ExecutionSession,
    ExecutionState,
)
from backend.core.execution.monitor import ExecutionMonitor
from backend.core.execution.retry import RetryManager
from backend.core.execution.rollback import RollbackManager
from backend.core.execution.task_runner import TaskRunner
from backend.core.planning.plan_graph import DependencyGraph

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Core runtime engine driving plan graph executions with safety checkpoints."""

    def __init__(self) -> None:
        self.sessions: Dict[str, ExecutionSession] = {}
        self.contexts: Dict[str, ExecutionContext] = {}
        self.checkpoint_mgr = CheckpointManager()
        self.monitor = ExecutionMonitor()
        self.event_bus = EventBus.get_instance()

    def start_execution(
        self,
        graph: DependencyGraph,
        initial_variables: Dict[str, Any],
        max_retries: int = 2,
    ) -> str:
        """Launches stateful execution of a plan graph."""
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        session = ExecutionSession(session_id=session_id, plan_id="plan_id")
        context = ExecutionContext(variables=dict(initial_variables))

        self.sessions[session_id] = session
        self.contexts[session_id] = context

        session.transition_to(ExecutionState.QUEUED)
        self.monitor.start_session(session_id)

        # Trigger execution loop synchronously or mock worker pool for tests
        self._run_loop(session_id, graph, max_retries)
        return session_id

    def pause_execution(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if session:
            session.transition_to(ExecutionState.PAUSED)
            self.checkpoint_mgr.save_checkpoint(session, self.contexts[session_id])

    def resume_execution(self, session_id: str, graph: DependencyGraph) -> None:
        session = self.sessions.get(session_id)
        if session and session.status == ExecutionState.PAUSED:
            session.transition_to(ExecutionState.RUNNING)
            self._run_loop(session_id, graph)

    def cancel_execution(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        context = self.contexts.get(session_id)
        if session and context:
            context.is_cancelled = True
            session.transition_to(ExecutionState.CANCELLED)
            self.checkpoint_mgr.delete_checkpoint(session_id)

    def trigger_recovery(self, session_id: str, graph: DependencyGraph) -> Optional[str]:
        """Loads and recovers a plan execution session from saved checkpoints."""
        restored = self.checkpoint_mgr.load_checkpoint(session_id)
        if not restored:
            logger.warning("No checkpoint found for session: %s", session_id)
            return None

        session, context = restored
        self.sessions[session_id] = session
        self.contexts[session_id] = context

        session.transition_to(ExecutionState.RUNNING)
        self._run_loop(session_id, graph)
        return session_id

    def _run_loop(
        self,
        session_id: str,
        graph: DependencyGraph,
        max_retries: int = 2,
    ) -> None:
        session = self.sessions[session_id]
        context = self.contexts[session_id]
        rollback_mgr = RollbackManager()

        session.transition_to(ExecutionState.RUNNING)

        try:
            # We schedule tasks layer-by-layer
            layers = graph.get_parallel_layers()
        except ValueError as exc:
            session.transition_to(ExecutionState.FAILED)
            return

        for layer in layers:
            # Run tasks in this execution layer
            for node_id in layer:
                if context.is_cancelled or session.status == ExecutionState.PAUSED:
                    return

                # If this node has already completed (e.g. from restored checkpoint), skip it!
                if node_id in session.completed_nodes:
                    continue

                node = graph.nodes[node_id]
                op = node.operator

                session.running_nodes.add(node_id)
                self.monitor.record_task_start(session_id, node_id)
                self.event_bus.publish(TaskStartedEvent(session_id, node_id))

                attempt = 0
                success = False
                last_error = ""

                # Retry Loop
                while attempt <= max_retries:
                    if context.is_cancelled:
                        session.running_nodes.discard(node_id)
                        return

                    try:
                        TaskRunner.execute(op, context)
                        success = True
                        break
                    except Exception as exc:
                        attempt += 1
                        last_error = str(exc)
                        self.monitor.record_failure(session_id)
                        self.event_bus.publish(TaskFailedEvent(session_id, node_id, last_error))

                        if attempt <= max_retries:
                            self.monitor.record_retry(session_id)
                            session.retry_counts[node_id] = attempt
                            # Calculate backoff delay and simulate/wait
                            delay = RetryManager.get_backoff_delay(attempt)
                            logger.info("Retrying node %s in %.1fs (attempt %d)", node_id, delay, attempt)
                            # In real runtime we'd sleep, but here we can wait or mock

                session.running_nodes.discard(node_id)
                self.monitor.record_task_end(session_id, node_id)

                if success:
                    session.completed_nodes.add(node_id)
                    rollback_mgr.record_completed(op)
                    self.event_bus.publish(TaskCompletedEvent(session_id, node_id))
                    # Save checkpoint on step success
                    self.checkpoint_mgr.save_checkpoint(session, context)
                else:
                    session.failed_nodes.add(node_id)
                    logger.error("Node %s failed completely after %d attempts.", node_id, attempt)
                    
                    # Trigger Rollback
                    session.transition_to(ExecutionState.ROLLING_BACK)
                    rollback_mgr.execute_rollback(context)
                    
                    session.transition_to(ExecutionState.FAILED)
                    self.checkpoint_mgr.delete_checkpoint(session_id)
                    return

        # Complete session
        if len(session.completed_nodes) == len(graph.nodes):
            session.progress = 100.0
            session.transition_to(ExecutionState.COMPLETED)
            self.checkpoint_mgr.delete_checkpoint(session_id)
            self.monitor.end_session(session_id)
