from __future__ import annotations
import concurrent.futures
import threading
import time
from typing import Any
from backend.core.orchestrator.base import Task, TaskResult, BaseAgent
from backend.core.orchestrator.context import SharedContext
from backend.core.orchestrator.message_bus import MessageBus
from backend.core.orchestrator.task_graph import TaskGraph
from backend.core.orchestrator.registry import ORCHESTRATOR_REGISTRY, AgentRegistry
from backend.core.logger import log_event

class TaskScheduler:
    def __init__(
        self,
        registry: AgentRegistry | None = None,
        message_bus: MessageBus | None = None,
        max_workers: int = 4,
    ):
        self.registry = registry or ORCHESTRATOR_REGISTRY
        self.message_bus = message_bus or MessageBus()
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="OrchestratorAgentWorker"
        )
        self._lock = threading.RLock()
        
        self._running_graphs: dict[str, TaskGraph] = {}
        self._contexts: dict[str, SharedContext] = {}
        self._cancellation_tokens: dict[str, bool] = {}  # graph_id -> cancelled
        self._active_futures: dict[str, list[concurrent.futures.Future]] = {}  # graph_id -> futures
        self._running_tasks: dict[str, Task] = {}  # task_id -> Task

    def run_graph(
        self,
        graph: TaskGraph,
        graph_id: str,
        initial_context: dict[str, Any] | None = None,
    ) -> SharedContext:
        """Run the task graph to completion, blocking the caller thread."""
        context = SharedContext(initial_context)
        
        with self._lock:
            self._running_graphs[graph_id] = graph
            self._contexts[graph_id] = context
            self._cancellation_tokens[graph_id] = False
            self._active_futures[graph_id] = []

        log_event("orchestrator_graph_start", f"Starting TaskGraph run: {graph_id}")
        self._dispatch_ready(graph, graph_id, context)

        # Wait until graph is finished
        while True:
            time.sleep(0.1)
            with self._lock:
                is_finished = graph.is_finished()
                is_cancelled = self._cancellation_tokens.get(graph_id, False)
            if is_finished or is_cancelled:
                break

        # Cleanup
        with self._lock:
            self._running_graphs.pop(graph_id, None)
            self._cancellation_tokens.pop(graph_id, None)
            self._active_futures.pop(graph_id, None)

        log_event("orchestrator_graph_end", f"Finished TaskGraph run: {graph_id}")
        return context

    def cancel_graph(self, graph_id: str) -> None:
        """Signal cancellation for all running/pending tasks in the graph."""
        with self._lock:
            self._cancellation_tokens[graph_id] = True
            graph = self._running_graphs.get(graph_id)
            if not graph:
                return

            for task in graph.tasks.values():
                if task.status in ("PENDING", "RUNNING"):
                    task.status = "CANCELLED"
                    try:
                        agent = self.registry.get(task.agent_name)
                        if agent:
                            agent.terminate(task.task_id)
                    except Exception as e:
                        log_event("orchestrator_cancellation_error", f"Error terminating agent task: {e}")

            futures = self._active_futures.get(graph_id, [])
            for future in futures:
                future.cancel()

    def _dispatch_ready(self, graph: TaskGraph, graph_id: str, context: SharedContext) -> None:
        with self._lock:
            if self._cancellation_tokens.get(graph_id, False):
                return
            ready_tasks = graph.get_ready_tasks()
            for task in ready_tasks:
                task.status = "RUNNING"
                future = self.executor.submit(self._execute_task, task, graph_id, context)
                self._active_futures[graph_id].append(future)

    def _execute_task(self, task: Task, graph_id: str, context: SharedContext) -> None:
        with self._lock:
            if self._cancellation_tokens.get(graph_id, False):
                task.status = "CANCELLED"
                return
            self._running_tasks[task.task_id] = task

        log_event("orchestrator_task_start", f"Running task {task.task_id} on agent {task.agent_name}")
        
        # ── K11: Register Action (Level 4) and Update Task (Level 3) ─────────
        action_node_id = f"{task.task_id}_action"
        try:
            from backend.core.goal_hierarchy import GoalHierarchy, HierarchyLevel
            # Update Task to ACTIVE
            GoalHierarchy.update_node(task.task_id, status="ACTIVE", progress=0.1)
            # Create Action node
            GoalHierarchy.add_node(
                node_id=action_node_id,
                parent_id=task.task_id,
                level=HierarchyLevel.ACTION,
                title=f"Agent {task.agent_name} executing {task.action}",
                status="ACTIVE",
                progress=0.1,
            )
        except Exception as e:
            log_event("scheduler_hierarchy_error", f"Error registering action node: {e}")

        try:
            agent = self.registry.get_or_raise(task.agent_name)
            agent.initialize()
            result = agent.execute(task, context)
            
            if result.success:
                with self._lock:
                    task.status = "COMPLETED"
                    task.output = result.output
                try:
                    from backend.core.goal_hierarchy import GoalHierarchy
                    GoalHierarchy.update_node(action_node_id, status="COMPLETED", progress=1.0)
                except Exception as e:
                    log_event("scheduler_hierarchy_error", f"Error completing action node: {e}")
                self.message_bus.publish(f"task/completed/{task.task_id}", result.output)
                self.message_bus.publish("task/completed", task.task_id)
            else:
                try:
                    from backend.core.goal_hierarchy import GoalHierarchy
                    GoalHierarchy.update_node(action_node_id, status="FAILED", progress=0.0)
                except Exception as e:
                    log_event("scheduler_hierarchy_error", f"Error failing action node: {e}")
                self._handle_failure(task, graph_id, context, result.error or "Unknown failure")
        except Exception as e:
            try:
                from backend.core.goal_hierarchy import GoalHierarchy
                GoalHierarchy.update_node(action_node_id, status="FAILED", progress=0.0)
            except Exception as ex:
                log_event("scheduler_hierarchy_error", f"Error failing action node: {ex}")
            self._handle_failure(task, graph_id, context, str(e))
        finally:
            with self._lock:
                self._running_tasks.pop(task.task_id, None)

            with self._lock:
                graph = self._running_graphs.get(graph_id)
            if graph:
                self._dispatch_ready(graph, graph_id, context)

    def _handle_failure(self, task: Task, graph_id: str, context: SharedContext, error_msg: str) -> None:
        max_attempts = getattr(task, "max_attempts", 3)
        task.retry_count += 1
        
        log_event(
            "orchestrator_task_failed",
            f"Task {task.task_id} failed (attempt {task.retry_count}/{max_attempts}): {error_msg}"
        )

        if task.retry_count < max_attempts:
            delay = min(10.0, 1.5 ** task.retry_count)
            log_event("orchestrator_task_retry", f"Scheduling retry for task {task.task_id} in {delay:.2f}s")
            
            def retry_dispatch():
                time.sleep(delay)
                with self._lock:
                    if self._cancellation_tokens.get(graph_id, False):
                        task.status = "CANCELLED"
                        return
                    task.status = "RUNNING"
                future = self.executor.submit(self._execute_task, task, graph_id, context)
                with self._lock:
                    if graph_id in self._active_futures:
                        self._active_futures[graph_id].append(future)

            threading.Thread(target=retry_dispatch, daemon=True).start()
        else:
            with self._lock:
                task.status = "FAILED"
                task.error = error_msg
                self.cancel_graph(graph_id)
            self.message_bus.publish(f"task/failed/{task.task_id}", error_msg)
            self.message_bus.publish("task/failed", task.task_id)


ORCHESTRATOR_SCHEDULER = TaskScheduler()
