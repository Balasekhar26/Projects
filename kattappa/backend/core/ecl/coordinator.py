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
    ) -> Dict[str, Any]:
        log_event("ecl_coordinator_start", f"Initiating ECL transaction: {goal_title}")

        # 1. Goal Decomposition
        decomp = ECLGoalDecomposer.decompose(goal_title, goal_desc)
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
        
        # Format task records
        steps = []
        for idx, t in enumerate(tasks_data):
            steps.append({
                "task_id": t["id"],
                "title": t["title"],
                "action": "execute_task_step",
                "params": {"goal_title": goal_title, "task_id": t["id"]},
            })

        # 2. Budget Management
        budget = ECLBudgetManager.calculate_budget(priority)

        # 3. Policy & Safety Verification
        valid, reason = ECLPolicyEngine.validate_plan(goal_title, steps)
        if not valid:
            log_event("ecl_coordinator_policy_halt", f"Policy halt triggered: {reason}")
            GoalHierarchy.update_node(goal_id, status="FAILED", progress=0.0)
            return {
                "success": False,
                "goal_id": goal_id,
                "decision": "HALT",
                "error": reason,
            }

        # 4. Counterfactual Simulation
        sim = ECLSimulationRunner.evaluate_viability(goal_title, steps)
        best_branch = sim["best_branch_id"]
        viability_score = sim["viability_score"]

        # 5. Resource & Model Routing
        routing_info = ECLRouter.route_task(goal_title)

        # 6. Build TaskGraph and Dispatch
        task_graph = TaskGraph()
        
        # Populate graph tasks
        prev_task_id = None
        for step in steps:
            task = Task(
                task_id=step["task_id"],
                agent_name="Executive",  # Routable to core executive agent
                action=step["action"],
                params=step["params"],
                dependencies=[prev_task_id] if prev_task_id else [],
            )
            task_graph.add_task(task)
            prev_task_id = step["task_id"]

        # Instantiate scheduler and run
        scheduler = TaskScheduler(max_workers=budget["micro_batch_size"])
        
        # Run graph execution in a separate execution record context
        initial_context = {
            "goal_id": goal_id,
            "budget": budget,
            "best_branch": best_branch,
            "routing_info": routing_info,
            "viability_score": viability_score,
        }
        
        log_event("ecl_coordinator_dispatch", f"Dispatching TaskGraph for goal: {goal_id}")
        context = scheduler.run_graph(task_graph, graph_id=goal_id, initial_context=initial_context)

        success = task_graph.is_finished()
        status = "COMPLETED" if success else "FAILED"
        GoalHierarchy.update_node(goal_id, status=status, progress=1.0 if success else 0.0)

        # Emit ECL_PLAN_EXECUTED event
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
                }
            )
            WSEEventBus.get_instance().publish(executed_event)
        except Exception as e:
            logger.error("Failed to publish ECL_PLAN_EXECUTED: %s", e)

        return {
            "success": success,
            "goal_id": goal_id,
            "status": status,
            "best_branch": best_branch,
            "viability_score": viability_score,
            "budget": budget,
            "routing": routing_info,
        }
