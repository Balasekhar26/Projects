from __future__ import annotations
import concurrent.futures
from dataclasses import dataclass, field
import logging
import os
import threading
import time
import uuid
from typing import Any
from backend.core.orchestrator.base import Task, TaskResult, BaseAgent
from backend.core.orchestrator.context import SharedContext
from backend.core.orchestrator.message_bus import MessageBus
from backend.core.orchestrator.task_graph import TaskGraph
from backend.core.orchestrator.registry import ORCHESTRATOR_REGISTRY, AgentRegistry
from backend.core.logger import log_event


@dataclass
class GraphExecutionState:
    graph_id: str
    generation_id: str
    cancelled: bool = False
    closed: bool = False
    deadline: float = 0.0
    cancel_event: threading.Event = field(default_factory=threading.Event)
    retry_threads: set[threading.Thread] = field(default_factory=set)
    futures: set[concurrent.futures.Future] = field(default_factory=set)


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
        self._graph_states: dict[str, GraphExecutionState] = {}
        self._running_tasks: dict[str, Task] = {}  # task_id -> Task

    def run_graph(
        self,
        graph: TaskGraph,
        graph_id: str,
        initial_context: dict[str, Any] | None = None,
        timeout: float = 120.0,
    ) -> SharedContext:
        """Run the task graph to completion, blocking the caller thread."""
        context = SharedContext(initial_context)
        generation_id = uuid.uuid4().hex
        deadline = time.monotonic() + timeout
        
        state = GraphExecutionState(
            graph_id=graph_id,
            generation_id=generation_id,
            deadline=deadline,
        )
        
        with self._lock:
            self._running_graphs[graph_id] = graph
            self._contexts[graph_id] = context
            self._graph_states[graph_id] = state

        log_event("orchestrator_graph_start", f"Starting TaskGraph run: {graph_id} (gen={generation_id})")
        self._dispatch_ready(graph, graph_id, context, state)

        timed_out = False
        while True:
            time.sleep(0.02)
            with self._lock:
                st = self._graph_states.get(graph_id)
                if not st or st.closed or st.cancelled:
                    break
                is_finished = graph.is_finished()
            if is_finished:
                break
            if time.monotonic() > deadline:
                timed_out = True
                log_event("orchestrator_graph_timeout", f"TaskGraph {graph_id} exceeded {timeout}s monotonic deadline, triggering cancellation")
                self.cancel_graph(graph_id, status="TIMEOUT")
                break

        if timed_out:
            context.set("timed_out", True)
            context.set("graph_status", "TIMEOUT")

        with self._lock:
            self._running_graphs.pop(graph_id, None)

        log_event("orchestrator_graph_end", f"Finished TaskGraph run: {graph_id} (timed_out={timed_out})")
        return context

    def cancel_graph(self, graph_id: str, status: str = "CANCELLED") -> None:
        """Signal cancellation for all running/pending tasks in the graph and shutdown pending futures."""
        with self._lock:
            state = self._graph_states.get(graph_id)
            if state:
                state.cancelled = True
                state.cancel_event.set()
                futures = list(state.futures)
            else:
                futures = []

            graph = self._running_graphs.get(graph_id)
            if graph:
                for task in graph.tasks.values():
                    if task.status in ("PENDING", "RUNNING"):
                        task.status = status
                        task.error = f"Execution halted due to {status}"
                        try:
                            agent = self.registry.get(task.agent_name)
                            if agent:
                                agent.terminate(task.task_id)
                        except Exception as e:
                            log_event("orchestrator_cancellation_error", f"Error terminating agent task: {e}")

            for future in futures:
                try:
                    future.cancel()
                except Exception:
                    pass

    def cancel_all_active_graphs(self) -> None:
        with self._lock:
            graph_ids = list(self._running_graphs.keys())
        for gid in graph_ids:
            self.cancel_graph(gid)

    def close(self, wait: bool = True) -> None:
        """Close scheduler, cancel running graphs, set cancel events, and shutdown executor."""
        with self._lock:
            graph_ids = list(self._graph_states.keys())
            for gid in graph_ids:
                state = self._graph_states.get(gid)
                if state:
                    state.closed = True
                    state.cancelled = True
                    state.cancel_event.set()
                self.cancel_graph(gid, status="CANCELLED")
                
            states = list(self._graph_states.values())

        # Cancel futures
        for st in states:
            for f in list(st.futures):
                try:
                    f.cancel()
                except Exception:
                    pass

        # Shutdown executor
        try:
            self.executor.shutdown(wait=wait, cancel_futures=True)
        except Exception as e:
            log_event("scheduler_shutdown_error", f"Error during executor shutdown: {e}")

        # Wait for retry threads
        for st in states:
            for t in list(st.retry_threads):
                if t.is_alive():
                    t.join(timeout=1.0)

    def check_cleanup_status(self, graph_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            active_graphs = len(self._running_graphs)
            active_futures = sum(
                sum(1 for f in st.futures if not f.done())
                for st in self._graph_states.values()
            )
            active_retry_workers = sum(
                sum(1 for t in st.retry_threads if t.is_alive())
                for st in self._graph_states.values()
            )
            running_tasks = len(self._running_tasks)
            executor_shutdown = getattr(self.executor, "_shutdown", False)
            running_worker_threads = sum(
                1 for t in threading.enumerate()
                if "OrchestratorAgentWorker" in t.name and t.is_alive()
            )

            cleanup_complete = (
                active_graphs == 0
                and active_futures == 0
                and active_retry_workers == 0
                and running_tasks == 0
            )

            return {
                "cleanup_complete": cleanup_complete,
                "active_graphs_remaining": active_graphs,
                "active_futures_remaining": active_futures,
                "active_retry_workers_remaining": active_retry_workers,
                "running_tasks_remaining": running_tasks,
                "running_worker_threads_remaining": running_worker_threads,
                "executor_shutdown": executor_shutdown,
            }

    def _dispatch_ready(
        self,
        graph: TaskGraph,
        graph_id: str,
        context: SharedContext,
        state: GraphExecutionState | None = None
    ) -> None:
        with self._lock:
            st = state or self._graph_states.get(graph_id)
            if not st or st.cancelled or st.closed or st.cancel_event.is_set():
                return
            ready_tasks = graph.get_ready_tasks()
            for task in ready_tasks:
                task.status = "RUNNING"
                future = self.executor.submit(self._execute_task, task, graph_id, context, st.generation_id)
                st.futures.add(future)
                future.add_done_callback(lambda f, s=st: s.futures.discard(f))

    def _execute_task(
        self,
        task: Task,
        graph_id: str,
        context: SharedContext,
        expected_gen: str
    ) -> None:
        with self._lock:
            st = self._graph_states.get(graph_id)
            if not st or st.cancelled or st.closed or st.generation_id != expected_gen or st.cancel_event.is_set():
                task.status = "CANCELLED"
                return
            self._running_tasks[task.task_id] = task

        log_event("orchestrator_task_start", f"Running task {task.task_id} on agent {task.agent_name}")
        
        # Action node registration
        action_node_id = f"{task.task_id}_action"
        try:
            from backend.core.goal_hierarchy import GoalHierarchy, HierarchyLevel
            GoalHierarchy.update_node(task.task_id, status="ACTIVE", progress=0.1)
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
                self._handle_failure(task, graph_id, context, result.error or "Unknown failure", expected_gen)
        except Exception as e:
            try:
                from backend.core.goal_hierarchy import GoalHierarchy
                GoalHierarchy.update_node(action_node_id, status="FAILED", progress=0.0)
            except Exception as ex:
                log_event("scheduler_hierarchy_error", f"Error failing action node: {ex}")
            self._handle_failure(task, graph_id, context, str(e), expected_gen)
        finally:
            with self._lock:
                self._running_tasks.pop(task.task_id, None)

            with self._lock:
                graph = self._running_graphs.get(graph_id)
                st = self._graph_states.get(graph_id)
            if graph and st:
                self._dispatch_ready(graph, graph_id, context, st)

    def _handle_failure(
        self,
        task: Task,
        graph_id: str,
        context: SharedContext,
        error_msg: str,
        expected_gen: str
    ) -> None:
        max_attempts = getattr(task, "max_attempts", 3)
        task.retry_count += 1
        
        log_event(
            "orchestrator_task_failed",
            f"Task {task.task_id} failed (attempt {task.retry_count}/{max_attempts}): {error_msg}"
        )

        if task.retry_count < max_attempts:
            delay = min(10.0, 1.5 ** task.retry_count)
            log_event("orchestrator_task_retry", f"Scheduling retry for task {task.task_id} in {delay:.2f}s")
            
            def retry_dispatch(target_gen: str):
                cur_thread = threading.current_thread()
                with self._lock:
                    st = self._graph_states.get(graph_id)
                    if st:
                        st.retry_threads.add(cur_thread)

                try:
                    with self._lock:
                        st = self._graph_states.get(graph_id)
                        if not st or st.cancelled or st.closed or st.generation_id != target_gen or st.cancel_event.is_set():
                            task.status = "CANCELLED"
                            return
                        evt = st.cancel_event

                    interrupted = evt.wait(timeout=delay)

                    with self._lock:
                        st = self._graph_states.get(graph_id)
                        if interrupted or not st or st.cancelled or st.closed or st.generation_id != target_gen or time.monotonic() > st.deadline:
                            task.status = "CANCELLED"
                            return
                        task.status = "RUNNING"

                    future = self.executor.submit(self._execute_task, task, graph_id, context, target_gen)
                    with self._lock:
                        st = self._graph_states.get(graph_id)
                        if st:
                            st.futures.add(future)
                            future.add_done_callback(lambda f: st.futures.discard(f) if st else None)
                finally:
                    with self._lock:
                        st = self._graph_states.get(graph_id)
                        if st:
                            st.retry_threads.discard(cur_thread)

            t = threading.Thread(target=retry_dispatch, args=(expected_gen,), daemon=True)
            with self._lock:
                st = self._graph_states.get(graph_id)
                if st:
                    st.retry_threads.add(t)
            t.start()
        else:
            with self._lock:
                graph = self._running_graphs.get(graph_id)
            if graph:
                from backend.core.orchestrator.replanner import FailureReplanner
                try:
                    replan_ok = FailureReplanner.analyze_and_replan(graph, task, error_msg, context)
                except Exception as ex:
                    log_event("replanner_exception", f"Error during replan: {ex}")
                    replan_ok = False
                
                if replan_ok:
                    log_event("orchestrator_replan_triggered", f"Replanned graph {graph_id} around failed task {task.task_id}")
                    with self._lock:
                        st = self._graph_states.get(graph_id)
                    if st:
                        self._dispatch_ready(graph, graph_id, context, st)
                    return

            with self._lock:
                task.status = "FAILED"
                task.error = error_msg
                self.cancel_graph(graph_id)
            self.message_bus.publish(f"task/failed/{task.task_id}", error_msg)
            self.message_bus.publish("task/failed", task.task_id)


ORCHESTRATOR_SCHEDULER = TaskScheduler()
