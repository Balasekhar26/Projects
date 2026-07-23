from __future__ import annotations

import logging
import uuid
import time
from typing import Any, Dict, List

from backend.core.ecl.goal_decomposer import ECLGoalDecomposer
from backend.core.ecl.budget_manager import ECLBudgetManager
from backend.core.ecl.policy_engine import ECLPolicyEngine
from backend.core.ecl.simulation_runner import ECLSimulationRunner
from backend.core.ecl.router import ECLRouter
from backend.core.goal_hierarchy import GoalHierarchy
from backend.core.orchestrator.scheduler import TaskScheduler
from backend.core.orchestrator.task_graph import TaskGraph, Task
from backend.core.logger import log_event
from backend.core.ledger.models.enums import EventType
from backend.core.ledger.models.event import LedgerEvent
from backend.core.wse.event_bus import WSEEventBus

logger = logging.getLogger(__name__)


class ECLCoordinator:
    """Orchestrates the entire Executive Cognition Layer (ECL) transaction flow."""

    @classmethod
    def plan_and_execute(
        cls,
        goal_title: str,
        goal_desc: str = "",
        priority: str = "MEDIUM",
        timeout: float = 120.0,
    ) -> Dict[str, Any]:
        log_event("ecl_coordinator_start", f"Initiating ECL transaction: {goal_title}")
        phase_timings: Dict[str, float] = {}
        
        # 1. Goal Decomposition
        t0 = time.monotonic()
        decomp = ECLGoalDecomposer.decompose(goal_title, goal_desc)
        phase_timings["goal_decomposition"] = round((time.monotonic() - t0) * 1000, 2)
        
        goal_id = decomp["goal_id"]
        registered_nodes = decomp["registered_nodes"]

        # Emit ECL_GOAL_DECOMPOSED event
        try:
            decomposed_event = LedgerEvent(
                event_id=f"evt_decomp_{uuid.uuid4().hex[:12]}",
                parent_event_ids=[],
                goal_id=goal_id,
                session_id="",
                correlation_id=f"corr_{uuid.uuid4().hex[:8]}",
                timestamp_utc=time.time(),
                actor="ecl_coordinator",
                subsystem="ecl",
                event_type=EventType.ECL_GOAL_DECOMPOSED,
                payload={
                    "goal_id": goal_id,
                    "goal_title": goal_title,
                    "goal_desc": goal_desc,
                    "registered_nodes": registered_nodes,
                }
            )
            WSEEventBus.get_instance().publish(decomposed_event)
        except Exception as e:
            logger.error("Failed to publish ECL_GOAL_DECOMPOSED: %s", e)

        # Parse Level 3 Tasks for execution
        tasks_data = [n for n in registered_nodes if n["level"] == "TASK"]
        
        steps = []
        for idx, t in enumerate(tasks_data):
            steps.append({
                "task_id": t["id"],
                "title": t["title"],
                "action": "execute_task_step",
                "params": {"goal_title": goal_title, "task_id": t["id"]},
            })

        # 2. Budget Management
        t0 = time.monotonic()
        budget = ECLBudgetManager.calculate_budget(priority)
        phase_timings["budget_allocation"] = round((time.monotonic() - t0) * 1000, 2)

        # 3. Policy & Safety Verification
        t0 = time.monotonic()
        valid, reason = ECLPolicyEngine.validate_plan(goal_title, steps)
        phase_timings["policy_validation"] = round((time.monotonic() - t0) * 1000, 2)
        if not valid:
            log_event("ecl_coordinator_policy_halt", f"Policy halt triggered: {reason}")
            GoalHierarchy.update_node(goal_id, status="FAILED", progress=0.0)
            return {
                "success": False,
                "status": "FAILED",
                "goal_id": goal_id,
                "failed_phase": "policy_validation",
                "error_type": "PolicyHalt",
                "error_message": reason,
                "phase_timings": phase_timings,
                "cleanup_complete": True,
            }

        # 4. Counterfactual Simulation
        t0 = time.monotonic()
        sim = ECLSimulationRunner.evaluate_viability(goal_title, steps)
        phase_timings["simulation"] = round((time.monotonic() - t0) * 1000, 2)
        best_branch = sim["best_branch_id"]
        viability_score = sim["viability_score"]

        # 5. Resource & Model Routing
        t0 = time.monotonic()
        routing_info = ECLRouter.route_task(goal_title)
        phase_timings["routing"] = round((time.monotonic() - t0) * 1000, 2)

        # 6. Build TaskGraph and Dispatch
        task_graph = TaskGraph()
        prev_task_id = None
        for step in steps:
            task = Task(
                task_id=step["task_id"],
                agent_name="Executive",
                action=step["action"],
                params=step["params"],
                dependencies=[prev_task_id] if prev_task_id else [],
            )
            task_graph.add_task(task)
            prev_task_id = step["task_id"]

        scheduler = TaskScheduler(max_workers=budget["micro_batch_size"])
        initial_context = {
            "goal_id": goal_id,
            "budget": budget,
            "best_branch": best_branch,
            "routing_info": routing_info,
            "viability_score": viability_score,
        }
        
        log_event("ecl_coordinator_dispatch", f"Dispatching TaskGraph for goal: {goal_id}")
        t0 = time.monotonic()
        try:
            context = scheduler.run_graph(task_graph, graph_id=goal_id, initial_context=initial_context, timeout=timeout)
        finally:
            scheduler.close(wait=True)
        phase_timings["task_graph_execution"] = round((time.monotonic() - t0) * 1000, 2)

        cleanup_details = scheduler.check_cleanup_status(goal_id)

        task_states = {
            task.task_id: task.status
            for task in task_graph.tasks.values()
        }

        completed_count = sum(1 for s in task_states.values() if s == "COMPLETED")
        failed_count = sum(1 for s in task_states.values() if s == "FAILED")
        cancelled_count = sum(1 for s in task_states.values() if s == "CANCELLED")
        timed_out_count = sum(1 for s in task_states.values() if s == "TIMEOUT")

        all_completed = bool(task_states) and all(s == "COMPLETED" for s in task_states.values())
        any_failed = any(s == "FAILED" for s in task_states.values())
        any_cancelled = any(s == "CANCELLED" for s in task_states.values())
        any_timeout = any(s == "TIMEOUT" for s in task_states.values()) or context.get("timed_out", False)

        timed_out = any_timeout
        cleanup_complete = cleanup_details["cleanup_complete"]
        success = all_completed and not timed_out and cleanup_complete

        if all_completed and not timed_out and cleanup_complete:
            status = "COMPLETED"
        elif any_timeout:
            status = "TIMEOUT"
        elif any_cancelled:
            status = "CANCELLED"
        elif any_failed:
            status = "FAILED"
        else:
            status = "FAILED"

        GoalHierarchy.update_node(goal_id, status=status, progress=1.0 if success else 0.0)

        # 7. Ledger Commit & Event Emission
        t0 = time.monotonic()
        try:
            executed_event = LedgerEvent(
                event_id=f"evt_exec_{uuid.uuid4().hex[:12]}",
                parent_event_ids=[],
                goal_id=goal_id,
                session_id="",
                correlation_id=f"corr_{uuid.uuid4().hex[:8]}",
                timestamp_utc=time.time(),
                actor="ecl_coordinator",
                subsystem="ecl",
                event_type=EventType.ECL_PLAN_EXECUTED,
                payload={
                    "goal_id": goal_id,
                    "status": status,
                    "success": success,
                    "best_branch": best_branch,
                    "viability_score": viability_score,
                    "budget": budget,
                    "routing": routing_info,
                    "phase_timings": phase_timings,
                    "task_states": task_states,
                    "cleanup_complete": cleanup_complete,
                }
            )
            WSEEventBus.get_instance().publish(executed_event)
        except Exception as e:
            logger.error("Failed to publish ECL_PLAN_EXECUTED: %s", e)
        phase_timings["ledger_commit"] = round((time.monotonic() - t0) * 1000, 2)

        failed_phase = "task_graph_execution" if not success else None
        error_msg = "TaskGraph execution timed out" if timed_out else (None if success else "TaskGraph execution failed")

        return {
            "success": success,
            "status": status,
            "goal_id": goal_id,
            "failed_phase": failed_phase,
            "error_type": "TimeoutError" if timed_out else ("TaskError" if not success else None),
            "error_message": error_msg,
            "phase_timings": phase_timings,
            "best_branch": best_branch,
            "viability_score": viability_score,
            "budget": budget,
            "routing": routing_info,
            "task_states": task_states,
            "completed_task_count": completed_count,
            "failed_task_count": failed_count,
            "cancelled_task_count": cancelled_count,
            "timed_out_task_count": timed_out_count,
            "cleanup_complete": cleanup_complete,
            "cleanup_details": cleanup_details,
        }
